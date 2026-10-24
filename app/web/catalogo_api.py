"""Endpoints para dar de alta clientes, productos y apodos.
Siempre por decisión del tendero: la IA nunca crea registros."""
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.catalogo import RegistroInvalido, agregar_alias, crear_cliente, crear_producto

router = APIRouter(prefix="/api", tags=["catalogo"])


class ClienteNuevo(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    alias: list[str] = []
    confirmar_duplicado: bool = False


class ProductoNuevo(BaseModel):
    nombre: str
    precio_ref: float
    confirmar_duplicado: bool = False


class AliasNuevo(BaseModel):
    alias: str


def _rechazo(e: RegistroInvalido) -> JSONResponse:
    """409 si hay parecidos (el tendero debe decidir); 422 si los datos no son válidos."""
    estado = 409 if e.parecidos else 422
    return JSONResponse(
        status_code=estado, content={"errores": e.errores, "parecidos": e.parecidos}
    )


@router.post("/clientes", status_code=201)
def post_cliente(c: ClienteNuevo):
    try:
        return crear_cliente(c.nombre, c.telefono, c.alias, c.confirmar_duplicado)
    except RegistroInvalido as e:
        return _rechazo(e)


@router.post("/productos", status_code=201)
def post_producto(p: ProductoNuevo):
    try:
        return crear_producto(p.nombre, p.precio_ref, p.confirmar_duplicado)
    except RegistroInvalido as e:
        return _rechazo(e)


@router.post("/clientes/{cliente_id}/alias", status_code=201)
def post_alias(cliente_id: int, a: AliasNuevo):
    try:
        return agregar_alias(cliente_id, a.alias)
    except RegistroInvalido as e:
        return _rechazo(e)