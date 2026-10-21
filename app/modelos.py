"""Contrato del movimiento YA CONFIRMADO por el tendero (con ids de la BD)."""
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


class ItemConfirmado(BaseModel):
    producto_id: int
    cantidad: Decimal
    precio_unitario: Decimal


class MovimientoConfirmado(BaseModel):
    cliente_id: Optional[int] = None
    tipo: Literal["venta", "fiado", "abono"]
    monto: Optional[Decimal] = None
    items: list[ItemConfirmado] = []
    texto_original: Optional[str] = None