"""Guardado determinista: valida, guarda en una sola transacción y calcula el saldo."""
from decimal import Decimal
from typing import Optional

from app.db import get_conn
from app.modelos import MovimientoConfirmado
from app.validaciones import MovimientoInvalido, validar_movimiento


def saldo_cliente(conn, cliente_id: int) -> Decimal:
    """Saldo = fiados - abonos (lo calcula la vista `saldos`)."""
    fila = conn.execute(
        "SELECT saldo FROM saldos WHERE cliente_id = %s", (cliente_id,)
    ).fetchone()
    return fila["saldo"] if fila else Decimal("0")


def _verificar_existencias(conn, m: MovimientoConfirmado) -> list[str]:
    errores = []
    if m.cliente_id is not None:
        c = conn.execute(
            "SELECT activo FROM clientes WHERE id = %s", (m.cliente_id,)
        ).fetchone()
        if c is None or not c["activo"]:
            errores.append(f"El cliente {m.cliente_id} no existe o está inactivo.")
    for i in m.items:
        p = conn.execute(
            "SELECT 1 FROM productos WHERE id = %s", (i.producto_id,)
        ).fetchone()
        if p is None:
            errores.append(f"El producto {i.producto_id} no existe.")
    return errores


def _guardar(conn, m: MovimientoConfirmado, importacion_id: Optional[int]) -> dict:
    errores = _verificar_existencias(conn, m)
    if errores:
        raise MovimientoInvalido(errores)

    fila = conn.execute(
        """INSERT INTO transacciones (importacion_id, cliente_id, tipo, monto, fecha_movimiento, nota)
           VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_DATE), %s) RETURNING id""",
        (importacion_id, m.cliente_id, m.tipo, m.monto, m.fecha, m.texto_original),
    ).fetchone()
    transaccion_id = fila["id"]

    for i in m.items:
        conn.execute(
            """INSERT INTO transaccion_items
                   (transaccion_id, producto_id, cantidad, precio_unitario)
               VALUES (%s, %s, %s, %s)""",
            (transaccion_id, i.producto_id, i.cantidad, i.precio_unitario),
        )

    saldo = saldo_cliente(conn, m.cliente_id) if m.cliente_id is not None else None
    return {"transaccion_id": transaccion_id, "saldo": saldo}


def guardar_movimiento(
    m: MovimientoConfirmado, importacion_id: Optional[int] = None, conn=None
) -> dict:
    """Valida y guarda un movimiento. Lanza MovimientoInvalido si no cumple las reglas.

    Si se pasa `conn`, usa esa conexión y NO confirma (sirve para pruebas con
    rollback). Si no, abre la suya y confirma al terminar sin errores."""
    errores = validar_movimiento(m)
    if errores:
        raise MovimientoInvalido(errores)

    if conn is not None:
        return _guardar(conn, m, importacion_id)
    with get_conn() as propia:
        return _guardar(propia, m, importacion_id)