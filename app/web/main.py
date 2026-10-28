import pathlib
import os
import time
from typing import Optional

import psycopg
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app.catalogo import RegistroInvalido, agregar_alias, crear_cliente, crear_producto
from app.db import get_conn
from app.herramientas import resolver_cliente, resolver_producto
from app.modelos import MovimientoConfirmado
from app.transacciones import guardar_movimiento
from app.validaciones import MovimientoInvalido

from app.ia import FalloProveedor, obtener_proveedor
from app.ia.presupuesto import Presupuesto
from .schemas import validar_hoja

app = FastAPI(title="Libreta de Fiados Inteligente (prueba)")

TIPOS_PERMITIDOS = {"image/jpeg", "image/png"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB: fotos mas pesadas suelen causar timeouts
CODIGOS_HTTP = {"timeout": 504, "cuota": 429, "tokens": 422}  # cualquier otro fallo de la IA -> 503


def _aviso_resolucion(etiqueta: str, texto: str, r: dict) -> str | None:
    nombres = " o ".join(c["nombre"] for c in r["candidatos"])
    if r["estado"] == "ambiguo":
        return f'{etiqueta} "{texto}" es ambiguo: puede ser {nombres}.'
    if r["estado"] == "no_encontrado":
        return f'{etiqueta} "{texto}" no esta en la base de datos.'
    return None


def resolver_en_bd(hoja) -> dict:
    """Consulta clientes y productos (solo lectura) y registra una traza por cada consulta."""
    datos = hoja.model_dump(mode="json")
    datos["bd_disponible"] = True
    datos["trazas"] = []

    def registrar(herramienta: str, entrada: str, r: dict, t0: float):
        nombres = [c["nombre"] for c in r["candidatos"]]
        datos["trazas"].append({
            "herramienta": herramienta,
            "entrada": entrada,
            "estado": r["estado"],
            "detalle": "candidatos: " + (", ".join(nombres) if nombres else "ninguno"),
            "ms": round((time.perf_counter() - t0) * 1000),
        })

    try:
        for mov in datos["movimientos"]:
            mov["cliente_resuelto"] = None
            if mov["cliente"]:
                t0 = time.perf_counter()
                r = resolver_cliente(mov["cliente"])
                registrar("buscar_cliente", mov["cliente"], r, t0)
                mov["cliente_resuelto"] = r
                aviso = _aviso_resolucion("El cliente", mov["cliente"], r)
                if aviso:
                    mov["advertencias"].append(aviso)
            for item in mov["items"]:
                t0 = time.perf_counter()
                r = resolver_producto(item["producto"])
                registrar("buscar_producto", item["producto"], r, t0)
                item["producto_resuelto"] = r
                aviso = _aviso_resolucion("El producto", item["producto"], r)
                if aviso:
                    mov["advertencias"].append(aviso)
    except Exception as e:
        # Fallo de la BD: la pagina lo avisa en vez de romperse
        print("No se pudo consultar la BD:", e)
        datos["bd_disponible"] = False
    return datos


def leer_hoja(img: bytes, mime: str, proveedor=None, trazas: list | None = None):
    """Pide la lectura a la IA y valida el contrato.
    Maneja los fallos: timeout, respuesta invalida, caida de la API y topes de uso.
    Un solo `Presupuesto` (tiempo total y tokens acumulados) cubre TODOS los intentos.
    `trazas`: lista a la que se agregan las trazas del agente y de los intentos invalidos.
    Devuelve (hoja, intentos_usados)."""
    trazas = trazas if trazas is not None else []
    try:
        proveedor = proveedor or obtener_proveedor()
        presupuesto = Presupuesto.desde_entorno()
    except ValueError as e:
        print("IA mal configurada:", e)
        raise HTTPException(
            status_code=503,
            detail="La IA no está configurada. Avisa a quien administra la app.",
        )
    correccion = None
    max_intentos = int(os.getenv("MAX_INTENTOS", "2"))
    for intento in range(max_intentos):
        t_intento = time.perf_counter()
        try:
            presupuesto.verificar()   # no se empieza otro intento sin tiempo o tokens
            texto = proveedor.leer_hoja(img, mime, correccion, trazas=trazas, presupuesto=presupuesto)
        except FalloProveedor as e:
            raise HTTPException(status_code=CODIGOS_HTTP.get(e.codigo, 503), detail=e.mensaje)

        try:
            hoja = validar_hoja(texto)
        except ValidationError as e:
            print(f"--- Intento {intento + 1}: respuesta cruda de la IA (no cumple el contrato) ---")
            print(texto)
            correccion = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:5]
            )
            trazas.append({
                "herramienta": "validar_hoja",
                "entrada": f"intento {intento + 1}",
                "estado": "invalido",
                "detalle": correccion,
                "ms": round((time.perf_counter() - t_intento) * 1000),
            })
            continue

        if not hoja.movimientos:
            raise HTTPException(
                status_code=422,
                detail="No encontré movimientos en esta foto. Prueba con otra más clara.",
            )
        return hoja, intento + 1

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
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    if len(img) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"La foto pesa más de {MAX_BYTES // (1024 * 1024)} MB. Sube una más liviana.",
        )

    trazas: list[dict] = []   # las llena leer_hoja (agente e intentos invalidos)
    t0 = time.perf_counter()
    try:
        hoja, intentos = leer_hoja(img, foto.content_type, trazas=trazas)
    except HTTPException as e:
        # El fallo tambien deja traza: la pantalla la muestra aunque no haya hoja que revisar
        trazas.insert(0, {
            "herramienta": "leer_hoja (Gemini)",
            "entrada": foto.filename or "foto",
            "estado": "error",
            "detalle": f"HTTP {e.status_code}: {e.detail}",
            "ms": round((time.perf_counter() - t0) * 1000),
        })
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail, "trazas": trazas})
    ms_ia = round((time.perf_counter() - t0) * 1000)

    datos = resolver_en_bd(hoja)
    lectura = {
        "herramienta": "leer_hoja (Gemini)",
        "entrada": foto.filename or "foto",
        "estado": "ok",
        "detalle": f"{len(hoja.movimientos)} movimiento(s) · intentos: {intentos}",
        "ms": ms_ia,
    }
    # Orden: la lectura, lo que consulto el agente y al final la resolucion determinista en la BD
    datos["trazas"] = [lectura] + trazas + datos["trazas"]
    return datos


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
