from app.herramientas import resolver_cliente, resolver_producto

CLIENTES = ["doña rosa", "Rosita", "Don pedro", "Luz", "Pedro", "Carlos"]
PRODUCTOS = ["arroz", "aroz", "panela", "pan", "leche", "ron"]


def mostrar(titulo, textos, resolver):
    print(f"=== {titulo} ===")
    for texto in textos:
        r = resolver(texto)
        cand = [f'{c["nombre"]} ({c["puntaje"]})' for c in r["candidatos"]]
        print(f"{texto!r:14} -> {r['estado']:14} {cand}")
    print()


mostrar("CLIENTES", CLIENTES, resolver_cliente)
mostrar("PRODUCTOS", PRODUCTOS, resolver_producto)