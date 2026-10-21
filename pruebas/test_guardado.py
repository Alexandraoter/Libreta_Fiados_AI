from decimal import Decimal

from app.db import get_conn
from app.modelos import ItemConfirmado, MovimientoConfirmado
from app.transacciones import guardar_movimiento
from app.validaciones import MovimientoInvalido

# ids de la BD de ejemplo: clientes 1=Rosa, 2=Pedro Gómez, 4=Luz;
# productos 1=Arroz, 2=Panela, 3=Leche, 7=Pan
CASOS = {
    "Doña Rosa: 3 arroz x 2800 = 8400 (debe guardar)": MovimientoConfirmado(
        cliente_id=1, tipo="fiado", monto=Decimal("8400"),
        items=[ItemConfirmado(producto_id=1, cantidad=3, precio_unitario=2800)],
        texto_original="doña rosa 3 arroz x 2800 = 8400",
    ),
    "Don Pedro: abono 5000 (debe guardar)": MovimientoConfirmado(
        cliente_id=2, tipo="abono", monto=Decimal("5000"),
        texto_original="Don pedro abono 5000",
    ),
    "Luz: 2 leche x 4200 = 9000 (suma mal hecha)": MovimientoConfirmado(
        cliente_id=4, tipo="fiado", monto=Decimal("9000"),
        items=[ItemConfirmado(producto_id=3, cantidad=2, precio_unitario=4200)],
        texto_original="Luz 2 leche x 4200 = 9000",
    ),
    "Rosita: panela y pan, sin total": MovimientoConfirmado(
        cliente_id=1, tipo="fiado", monto=None,
        items=[
            ItemConfirmado(producto_id=2, cantidad=1, precio_unitario=2500),
            ItemConfirmado(producto_id=7, cantidad=1, precio_unitario=1500),
        ],
        texto_original="Rosita 1 panela x 2500 y 1 pan 1500",
    ),
    "Abono sin cliente": MovimientoConfirmado(
        tipo="abono", monto=Decimal("1000"), texto_original="abono 1000",
    ),
    "Fiado a un cliente que no existe": MovimientoConfirmado(
        cliente_id=999, tipo="fiado", monto=Decimal("1000"),
        texto_original="fiado a nadie",
    ),
}


def contar(conn):
    return conn.execute("SELECT count(*) AS n FROM transacciones").fetchone()["n"]


with get_conn() as conn:
    antes = contar(conn)
    for titulo, mov in CASOS.items():
        try:
            r = guardar_movimiento(mov, conn=conn)
            print(f"GUARDADO  | {titulo} -> saldo {r['saldo']}")
        except MovimientoInvalido as e:
            print(f"RECHAZADO | {titulo}")
            for err in e.errores:
                print("            *", err)
    durante = contar(conn)
    conn.rollback()  # deshace todo: la prueba no deja rastro en la BD
    despues = contar(conn)

print()
print(f"Transacciones: antes={antes}, durante={durante}, despues={despues}")