"""Contrato de datos de la extraccion (coincide con db/01_schema.sql)."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Item(BaseModel):
    producto: str = Field(min_length=1)
    cantidad: float = Field(gt=0)                        # CHECK cantidad > 0
    precio_unitario: Optional[float] = Field(default=None, ge=0)


class Movimiento(BaseModel):
    cliente: Optional[str] = None
    tipo: Literal["venta", "fiado", "abono"]             # CHECK de la BD
    monto: Optional[float] = Field(default=None, gt=0)   # CHECK monto > 0
    fecha: Optional[date] = None
    items: list[Item] = []
    texto_original: str
    advertencias: list[str] = []                         # las llena el codigo, no la IA


class Hoja(BaseModel):
    movimientos: list[Movimiento]


def calcular_advertencias(m: Movimiento) -> list[str]:
    """Reglas deterministas. La IA propone; este codigo revisa."""
    avisos = []

    if m.tipo in ("fiado", "abono") and not m.cliente:
        avisos.append("Falta el cliente (obligatorio en fiado y abono).")

    if m.tipo == "abono" and m.items:
        avisos.append("Un abono no deberia traer productos.")

    puede_sumar = bool(m.items) and all(i.precio_unitario is not None for i in m.items)
    suma = sum(i.cantidad * i.precio_unitario for i in m.items) if puede_sumar else None

    if m.monto is None:
        if suma is not None:
            avisos.append(f"El cuaderno no trae el total (los productos suman {suma:,.0f}).")
        else:
            avisos.append("Falta el monto y no hay datos para calcularlo.")
    elif suma is not None and abs(suma - m.monto) >= 0.01:
        avisos.append(
            f"No cuadra: los productos suman {suma:,.0f} pero el cuaderno dice {m.monto:,.0f}."
        )

    return avisos


def validar_hoja(texto_json: str) -> Hoja:
    """Valida el contrato (puede lanzar ValidationError) y agrega advertencias."""
    hoja = Hoja.model_validate_json(texto_json)
    for m in hoja.movimientos:
        m.advertencias = calcular_advertencias(m)
    return hoja
    