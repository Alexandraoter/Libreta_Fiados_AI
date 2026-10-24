from datetime import date, timedelta
from decimal import Decimal

from app.db import get_conn
from app.modelos import MovimientoConfirmado
from app.transacciones import guardar_movimiento
from app.validaciones import MovimientoInvalido


def ultima_fecha(conn):
    return conn.execute(
        "SELECT fecha_movimiento FROM transacciones ORDER BY id DESC LIMIT 1"
    ).fetchone()["fecha_movimiento"]


with get_conn() as conn:
    guardar_movimiento(
        MovimientoConfirmado(cliente_id=4, tipo="abono", monto=Decimal("1000"),
                             fecha=date(2026, 10, 1)),
        conn=conn,
    )
    print("Con fecha del cuaderno ->", ultima_fecha(conn), "(esperado 2026-10-01)")

    guardar_movimiento(
        MovimientoConfirmado(cliente_id=4, tipo="abono", monto=Decimal("1000")),
        conn=conn,
    )
    print("Sin fecha              ->", ultima_fecha(conn), f"(esperado hoy, {date.today()})")

    try:
        guardar_movimiento(
            MovimientoConfirmado(cliente_id=4, tipo="abono", monto=Decimal("1000"),
                                 fecha=date.today() + timedelta(days=5)),
            conn=conn,
        )
    except MovimientoInvalido as e:
        print("Fecha futura           -> RECHAZADO:", e.errores[0])

    conn.rollback()  # no deja nada en la BD