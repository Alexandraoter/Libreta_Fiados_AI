"""Consultas de SOLO LECTURA sobre la base de datos (saldos, historial, resumen).

Nunca escriben. Todo el SQL usa parámetros (%s / %(x)s): nada se concatena.
"""
from datetime import date
from typing import Optional

from app.db import get_conn


def deudores(solo_con_deuda: bool = True) -> list[dict]:
    """Saldo de cada cliente activo, de mayor a menor deuda."""
    sql = """
        SELECT s.cliente_id, s.nombre, s.saldo::float AS saldo
        FROM saldos s JOIN clientes c ON c.id = s.cliente_id
        WHERE c.activo {filtro}
        ORDER BY s.saldo DESC, s.nombre
    """.format(filtro="AND s.saldo > 0" if solo_con_deuda else "")
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def detalle_cliente(cliente_id: int, limite: int = 50) -> Optional[dict]:
    """Saldo + últimos movimientos (con sus productos) de un cliente."""
    with get_conn() as conn:
        c = conn.execute(
            "SELECT c.id, c.nombre, c.telefono, s.saldo::float AS saldo "
            "FROM clientes c JOIN saldos s ON s.cliente_id = c.id WHERE c.id = %s",
            (cliente_id,),
        ).fetchone()
        if c is None:
            return None
        c["movimientos"] = _movimientos(
            conn, {"cliente_id": cliente_id, "limite": limite}
        )
    return c


def _movimientos(conn, f: dict) -> list[dict]:
    sql = """
        SELECT t.id, t.fecha_movimiento::text AS fecha, t.tipo, t.monto::float AS monto,
               t.nota, c.nombre AS cliente,
               COALESCE(json_agg(json_build_object(
                   'producto', p.nombre, 'cantidad', i.cantidad::float,
                   'precio_unitario', i.precio_unitario::float))
                   FILTER (WHERE i.id IS NOT NULL), '[]') AS items
        FROM transacciones t
        LEFT JOIN clientes c ON c.id = t.cliente_id
        LEFT JOIN transaccion_items i ON i.transaccion_id = t.id
        LEFT JOIN productos p ON p.id = i.producto_id
        WHERE (%(cliente_id)s::int  IS NULL OR t.cliente_id = %(cliente_id)s)
          AND (%(tipo)s::text       IS NULL OR t.tipo = %(tipo)s)
          AND (%(desde)s::date      IS NULL OR t.fecha_movimiento >= %(desde)s)
          AND (%(hasta)s::date      IS NULL OR t.fecha_movimiento <= %(hasta)s)
        GROUP BY t.id, c.nombre
        ORDER BY t.fecha_movimiento DESC, t.id DESC
        LIMIT %(limite)s
    """
    params = {"cliente_id": None, "tipo": None, "desde": None, "hasta": None, "limite": 50}
    params.update(f)
    return conn.execute(sql, params).fetchall()


def movimientos(
    cliente_id: Optional[int] = None,
    tipo: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    limite: int = 50,
) -> list[dict]:
    with get_conn() as conn:
        return _movimientos(
            conn,
            {"cliente_id": cliente_id, "tipo": tipo, "desde": desde,
             "hasta": hasta, "limite": limite},
        )


def resumen(desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    """Totales por tipo en un rango de fechas + deuda total actual."""
    with get_conn() as conn:
        filas = conn.execute(
            """SELECT tipo, COUNT(*) AS cantidad, COALESCE(SUM(monto), 0)::float AS total
               FROM transacciones
               WHERE (%(d)s::date IS NULL OR fecha_movimiento >= %(d)s)
                 AND (%(h)s::date IS NULL OR fecha_movimiento <= %(h)s)
               GROUP BY tipo""",
            {"d": desde, "h": hasta},
        ).fetchall()
        deuda = conn.execute(
            "SELECT COALESCE(SUM(saldo), 0)::float AS total FROM saldos WHERE saldo > 0"
        ).fetchone()["total"]
    por_tipo = {t: {"cantidad": 0, "total": 0.0} for t in ("venta", "fiado", "abono")}
    for f in filas:
        por_tipo[f["tipo"]] = {"cantidad": f["cantidad"], "total": f["total"]}
    return {"por_tipo": por_tipo, "deuda_total_actual": deuda}


def productos_mas_vendidos(
    desde: Optional[date] = None, hasta: Optional[date] = None, limite: int = 10
) -> list[dict]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT p.nombre, SUM(i.cantidad)::float AS unidades,
                      SUM(i.subtotal)::float AS total
               FROM transaccion_items i
               JOIN transacciones t ON t.id = i.transaccion_id
               JOIN productos p ON p.id = i.producto_id
               WHERE (%(d)s::date IS NULL OR t.fecha_movimiento >= %(d)s)
                 AND (%(h)s::date IS NULL OR t.fecha_movimiento <= %(h)s)
               GROUP BY p.nombre ORDER BY unidades DESC LIMIT %(l)s""",
            {"d": desde, "h": hasta, "l": limite},
        ).fetchall()