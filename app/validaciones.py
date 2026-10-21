"""Reglas de negocio deterministas. Si algo falla, NO se guarda nada."""
from decimal import Decimal

from app.modelos import MovimientoConfirmado


class MovimientoInvalido(Exception):
    """El movimiento no cumple las reglas; .errores trae los motivos."""

    def __init__(self, errores: list[str]):
        super().__init__("; ".join(errores))
        self.errores = errores


def suma_items(m: MovimientoConfirmado) -> Decimal:
    return sum((i.cantidad * i.precio_unitario for i in m.items), Decimal("0"))


def validar_movimiento(m: MovimientoConfirmado) -> list[str]:
    """Devuelve la lista de errores (vacía si todo está bien)."""
    errores = []
    linea = f' Línea: "{m.texto_original}"' if m.texto_original else ""

    if m.tipo in ("fiado", "abono") and m.cliente_id is None:
        errores.append(f"Un {m.tipo} necesita cliente.{linea}")

    if m.tipo == "abono" and m.items:
        errores.append(f"Un abono no lleva productos.{linea}")

    for i in m.items:
        if i.cantidad <= 0:
            errores.append(f"La cantidad debe ser mayor que cero.{linea}")
        if i.precio_unitario < 0:
            errores.append(f"El precio no puede ser negativo.{linea}")

    if m.monto is None:
        if m.items:
            errores.append(
                f"Falta el monto del cuaderno (los productos suman "
                f"{suma_items(m):,.0f}).{linea}"
            )
        else:
            errores.append(f"Falta el monto y no hay productos para comprobarlo.{linea}")
    elif m.monto <= 0:
        errores.append(f"El monto debe ser mayor que cero.{linea}")
    elif m.items and suma_items(m) != m.monto:
        dif = m.monto - suma_items(m)
        errores.append(
            f"Los productos suman {suma_items(m):,.0f} pero el cuaderno dice "
            f"{m.monto:,.0f} (diferencia de {dif:+,.0f}).{linea}"
        )
    return errores