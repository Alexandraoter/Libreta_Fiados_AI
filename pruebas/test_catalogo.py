from app.catalogo import RegistroInvalido, agregar_alias, crear_cliente, crear_producto
from app.db import get_conn


def intentar(titulo, funcion, **kwargs):
    try:
        r = funcion(**kwargs)
        print(f"CREADO    | {titulo} -> {r}")
    except RegistroInvalido as e:
        print(f"RECHAZADO | {titulo}")
        for err in e.errores:
            print("            *", err)
        for p in e.parecidos:
            print(f'            ~ parecido: {p["nombre"]} ({p["puntaje"]})')


def contar(conn):
    q = lambda t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"]
    return q("clientes"), q("productos"), q("alias_cliente")


with get_conn() as conn:
    antes = contar(conn)

    intentar("Cliente nuevo con apodo", crear_cliente, conn=conn,
             nombre="  Marta  Lucía Pérez ", alias=["Doña Marta"])
    intentar("Cliente 'Rosita' (ya existe como apodo)", crear_cliente, conn=conn,
             nombre="Rosita")
    intentar("'Don Pedro' confirmado como otra persona", crear_cliente, conn=conn,
             nombre="Don Pedro", confirmar_duplicado=True)
    intentar("Cliente sin nombre", crear_cliente, conn=conn, nombre="  ")

    intentar("Producto nuevo", crear_producto, conn=conn,
             nombre="Café 250g", precio_ref=6500)
    intentar("Producto 'Arroz' (ya existe)", crear_producto, conn=conn,
             nombre="Arroz", precio_ref=3000)
    intentar("Producto con precio negativo", crear_producto, conn=conn,
             nombre="Jabón", precio_ref=-5)

    intentar("Apodo 'Rosi' para el cliente 1", agregar_alias, conn=conn,
             cliente_id=1, alias="Rosi")
    intentar("Apodo para un cliente que no existe", agregar_alias, conn=conn,
             cliente_id=999, alias="Fulana")

    durante = contar(conn)
    conn.rollback()  # deshace todo: la prueba no deja rastro
    despues = contar(conn)

print()
print("(clientes, productos, apodos)")
print(f"antes={antes}  durante={durante}  despues={despues}")