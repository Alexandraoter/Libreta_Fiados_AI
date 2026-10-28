"""Herramientas que el agente de Gemini puede pedir: buscar_cliente y buscar_producto.

Aquí solo viven (1) las DECLARACIONES en el formato de funciones de Gemini (FunctionDeclaration)
y (2) los EJECUTORES que las atienden. Los ejecutores usan app/herramientas.py, que es de SOLO
LECTURA: la IA sigue sin poder escribir en la base de datos.

Este archivo no importa `genai`: las declaraciones son diccionarios y gemini.py los convierte.
A propósito NO se le muestra a la IA el precio de referencia: podría "corregir" con él el
precio que el tendero escribió, y lo que cuenta es lo escrito en la libreta.
"""

DECLARACIONES = [
    {
        "name": "buscar_cliente",
        "description": (
            "Busca en la base de datos de la tienda al cliente que más se parece al nombre o "
            "apodo escrito en la libreta (solo lectura). Devuelve el estado (encontrado, ambiguo "
            "o no_encontrado) y los nombres candidatos con su puntaje de parecido de 0 a 1."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nombre": {
                    "type": "STRING",
                    "description": "Nombre o apodo del cliente tal como está escrito en la libreta. Ej: 'doña rosa'.",
                },
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "buscar_producto",
        "description": (
            "Busca en el catálogo de la tienda el producto que más se parece al texto escrito en "
            "la libreta (solo lectura). Devuelve el estado (encontrado, ambiguo o no_encontrado) "
            "y los nombres candidatos con su puntaje de parecido de 0 a 1."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "texto": {
                    "type": "STRING",
                    "description": "Producto tal como está escrito en la libreta. Ej: 'aroz'.",
                },
            },
            "required": ["texto"],
        },
    },
]


def _compactar(r: dict) -> dict:
    """Lo que ve la IA: estado y candidatos (sin ids ni precios)."""
    return {
        "estado": r["estado"],
        "candidatos": [{"nombre": c["nombre"], "puntaje": c["puntaje"]} for c in r["candidatos"]],
    }


def _buscar_cliente(args: dict) -> dict:
    from app.herramientas import resolver_cliente   # import perezoso: solo si el agente la pide

    return _compactar(resolver_cliente(str(args["nombre"])))


def _buscar_producto(args: dict) -> dict:
    from app.herramientas import resolver_producto

    return _compactar(resolver_producto(str(args["texto"])))


# nombre de la herramienta -> función que la ejecuta (recibe el dict de argumentos del modelo)
EJECUTORES = {
    "buscar_cliente": _buscar_cliente,
    "buscar_producto": _buscar_producto,
}
