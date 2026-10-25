import pathlib
from typing import Optional

import psycopg
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app.catalogo import RegistroInvalido, agregar_alias, crear_cliente, crear_producto
from app.db import get_conn
from app.herramientas import resolver_cliente, resolver_producto
from app.modelos import MovimientoConfirmado
from app.transacciones import guardar_movimiento
from app.validaciones import MovimientoInvalido

from .extractor import FalloProveedor, extraer_texto
from .schemas import validar_hoja

app = FastAPI(title="Libreta de Fiados Inteligente (prueba)")

TIPOS_PERMITIDOS = {"image/jpeg", "image/png"}


def _aviso_resolucion(etiqueta: str, texto: str, r: dict) -> str | None:
    nombres = " o ".join(c["nombre"] for c in r["candidatos"])
    if r["estado"] == "ambiguo":
        return f'{etiqueta} "{texto}" es ambiguo: puede ser {nombres}.'
    if r["estado"] == "no_encontrado":
        return f'{etiqueta} "{texto}" no esta en la base de datos.'
    return None


def resolver_en_bd(hoja) -> dict:
    datos = hoja.model_dump(mode="json")
    datos["bd_disponible"] = True
    try:
        for mov in datos["movimientos"]:
            mov["cliente_resuelto"] = None
            if mov["cliente"]:
                r = resolver_cliente(mov["cliente"])
                mov["cliente_resuelto"] = r
                aviso = _aviso_resolucion("El cliente", mov["cliente"], r)
                if aviso:
                    mov["advertencias"].append(aviso)
            for item in mov["items"]:
                r = resolver_producto(item["producto"])
                item["producto_resuelto"] = r
                aviso = _aviso_resolucion("El producto", item["producto"], r)
                if aviso:
                    mov["advertencias"].append(aviso)
    except Exception as e:
        # Fallo de la BD: la pagina lo avisa en vez de romperse
        print("No se pudo consultar la BD:", e)
        datos["bd_disponible"] = False
    return datos


def leer_hoja(img: bytes, mime: str):
    """Pide la lectura a Gemini y valida el contrato. Maneja los fallos 1, 2 y 3."""
    correccion = None
    for intento in range(2):
        try:
            texto = extraer_texto(img, mime, correccion)
        except FalloProveedor as e:
            codigo = 504 if e.codigo == "timeout" else 503
            raise HTTPException(status_code=codigo, detail=e.mensaje)

        try:
            hoja = validar_hoja(texto)
        except ValidationError as e:
            print(f"--- Intento {intento + 1}: respuesta cruda de Gemini (no cumple el contrato) ---")
            print(texto)
            correccion = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:5]
            )
            continue

        if not hoja.movimientos:
            raise HTTPException(
                status_code=422,
                detail="No encontré movimientos en esta foto. Prueba con otra más clara.",
            )
        return hoja

    raise HTTPException(
        status_code=422,
        detail="La IA no logró leer esta hoja. Prueba con otra foto más clara, con buena luz y la hoja plana.",
    )


@app.post("/api/extraer")
def extraer(foto: UploadFile = File(...)):
    if foto.content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(status_code=400, detail="Sube una imagen JPG o PNG.")
    img = foto.file.read()
    if not img:
        raise HTTPException(status_code=400, detail="El archivo esta vacio.")
    hoja = leer_hoja(img, foto.content_type)
    return resolver_en_bd(hoja)


@app.get("/api/catalogo")
def catalogo():
    """Clientes y productos activos, para los selectores de la pantalla."""
    try:
        with get_conn() as conn:
            clientes = conn.execute(
                "SELECT id, nombre FROM clientes WHERE activo ORDER BY nombre"
            ).fetchall()
            productos = conn.execute(
                "SELECT id, nombre, precio_ref::float AS precio_ref "
                "FROM productos WHERE activo ORDER BY nombre"
            ).fetchall()
    except Exception as e:
        print("No se pudo leer el catalogo:", e)
        raise HTTPException(status_code=503, detail="La base de datos no responde.")
    return {"clientes": clientes, "productos": productos}


# ---------- Altas por decision del tendero (app/catalogo.py) ----------
class NuevoCliente(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    alias: list[str] = []
    confirmar_duplicado: bool = False


class NuevoProducto(BaseModel):
    nombre: str
    precio_ref: float
    confirmar_duplicado: bool = False


class NuevoAlias(BaseModel):
    cliente_id: int
    alias: str


def _alta(funcion, **datos):
    """Ejecuta un alta. Rechazos de negocio -> 422 (con parecidos); BD caida -> 503."""
    try:
        return funcion(**datos)
    except RegistroInvalido as e:
        raise HTTPException(
            status_code=422, detail={"errores": e.errores, "parecidos": e.parecidos}
        )
    except psycopg.OperationalError as e:
        print("La BD no respondio en un alta:", e)
        raise HTTPException(
            status_code=503, detail="La base de datos no responde. No se guardó nada."
        )


@app.post("/api/clientes")
def nuevo_cliente(c: NuevoCliente):
    return _alta(
        crear_cliente, nombre=c.nombre, telefono=c.telefono, alias=c.alias,
        confirmar_duplicado=c.confirmar_duplicado,
    )


@app.post("/api/productos")
def nuevo_producto(p: NuevoProducto):
    return _alta(
        crear_producto, nombre=p.nombre, precio_ref=p.precio_ref,
        confirmar_duplicado=p.confirmar_duplicado,
    )


@app.post("/api/alias")
def nuevo_alias(a: NuevoAlias):
    return _alta(agregar_alias, cliente_id=a.cliente_id, alias=a.alias)


# ---------- Confirmacion del tendero (guardado de C) ----------
class Confirmacion(BaseModel):
    movimientos: list[MovimientoConfirmado]
    archivo: Optional[str] = None
    simular: bool = True   # por defecto NO guarda: la tabla es inmutable


@app.post("/api/confirmar")
def confirmar(c: Confirmacion):
    """Valida con las reglas de C y guarda toda la hoja en una sola transaccion.
    Si un movimiento falla, no se guarda ninguno."""
    if not c.movimientos:
        raise HTTPException(status_code=400, detail="No hay movimientos para guardar.")

    resultados = []
    try:
        with get_conn() as conn:
            nombres = {
                f["id"]: f["nombre"]
                for f in conn.execute("SELECT id, nombre FROM clientes").fetchall()
            }
            imp = conn.execute(
                "INSERT INTO importaciones (archivo, estado, confirmada_en) "
                "VALUES (%s, 'confirmada', now()) RETURNING id",
                (c.archivo,),
            ).fetchone()
            for m in c.movimientos:
                r = guardar_movimiento(m, imp["id"], conn=conn)
                r["cliente"] = nombres.get(m.cliente_id)
                r["tipo"] = m.tipo
                r["monto"] = m.monto
                resultados.append(r)
            if c.simular:
                conn.rollback()   # prueba: todo se deshace
    except MovimientoInvalido as e:
        raise HTTPException(status_code=422, detail={"errores": e.errores})
    except psycopg.OperationalError as e:
        print("La BD no respondio al guardar:", e)
        raise HTTPException(
            status_code=503,
            detail="La base de datos no responde. No se guardó nada.",
        )

    return {"guardado": not c.simular, "resultados": resultados}


# El frontend se sirve desde el mismo servidor.
# Va al final para que no tape las rutas /api.
app.mount(
    "/",
    StaticFiles(directory=pathlib.Path(__file__).parent / "static", html=True),
    name="static",
)
