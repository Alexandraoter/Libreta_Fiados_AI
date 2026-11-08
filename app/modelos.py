"""Contrato del movimiento YA CONFIRMADO por el tendero (con ids de la BD)."""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


# Solo topes MAXIMOS (evitan desbordar NUMERIC(12,2) y cuerpos enormes).
# Los minimos los sigue validando app/validaciones.py con sus mensajes de siempre.
class ItemConfirmado(BaseModel):
    producto_id: int
    cantidad: Decimal = Field(le=Decimal("100000"))
    precio_unitario: Decimal = Field(le=Decimal("10000000"))


class MovimientoConfirmado(BaseModel):
    cliente_id: Optional[int] = None
    tipo: Literal["venta", "fiado", "abono"]
    monto: Optional[Decimal] = Field(default=None, le=Decimal("9999999999"))
    fecha: Optional[date] = None
    items: list[ItemConfirmado] = Field(default=[], max_length=100)
    texto_original: Optional[str] = Field(default=None, max_length=500)