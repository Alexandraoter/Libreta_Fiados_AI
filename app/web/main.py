import pathlib
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app.db import get_conn
from app.transacciones import guardar_movimiento
from app.herramientas import resolver_cliente, resolver_producto
from app.modelos import MovimientoConfirmado
from app.validaciones import MovimientoInvalido

from .extractor import extraer_texto
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
        print("No se pudo consultar la BD:", e)
        datos["bd_disponible"] = False
    return datos


@app.post("/api/extraer")
def extraer(foto: UploadFile = File(...)):
    if foto.content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(status_code=400, detail="Sube una imagen JPG o PNG.")
    img = foto.file.read()
    if not img:
        raise HTTPException(status_code=400, detail="El archivo esta vacio.")
    try:
        texto = extraer_texto(img, foto.content_type)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    try:
        hoja = validar_hoja(texto)
    except ValidationError:
        print("--- Respuesta cruda de Gemini (no cumple el contrato) ---")
        print(texto)
        raise HTTPException(
            status_code=422,
            detail="La IA devolvio un JSON que no cumple el contrato. Intenta con otra foto.",
        )
    return resolver_en_bd(hoja)


@app.get("/api/catalogo")
def catalogo():
    """Clientes y productos activos, para los selectores de la pantalla."""
    with get_conn() as conn:
        clientes = conn.execute(
            "SELECT id, nombre FROM clientes WHERE activo ORDER BY nombre"
        ).fetchall()
        productos = conn.execute(
            "SELECT id, nombre, precio_ref::float AS precio_ref "
            "FROM productos WHERE activo ORDER BY nombre"
        ).fetchall()
    return {"clientes": clientes, "productos": productos}


class Confirmacion(BaseModel):
    movimientos: list[MovimientoConfirmado]
    archivo: Optional[str] = None
    simular: bool = True   # por defecto NO guarda: la tabla es inmutable


@app.post("/api/confirmar")
def confirmar(c: Confirmacion):
    """Valida con las reglas de C y guarda toda la hoja en una sola transaccion."""
    if not c.movimientos:
        raise HTTPException(status_code=400, detail="No hay movimientos para guardar.")

    resultados = []
    try:
        with get_conn() as conn:
            imp = conn.execute(
                "INSERT INTO importaciones (archivo, estado, confirmada_en) "
                "VALUES (%s, 'confirmada', now()) RETURNING id",
                (c.archivo,),
            ).fetchone()
            for m in c.movimientos:
                resultados.append(guardar_movimiento(m, imp["id"], conn=conn))
            if c.simular:
                conn.rollback()   # prueba: todo se deshace
    except MovimientoInvalido as e:
        raise HTTPException(status_code=422, detail={"errores": e.errores})

    return {"guardado": not c.simular, "resultados": resultados}


app.mount(
    "/",
    StaticFiles(directory=pathlib.Path(__file__).parent / "static", html=True),
    name="static",
)