"""Herramientas de SOLO LECTURA: traducen lo que escribió el tendero
("doña rosa", "aroz") a un cliente o producto real de la base de datos.

Nunca escriben en la BD. Si hay duda, devuelven los candidatos para que
decida el tendero; el sistema no adivina."""
from app.db import get_conn

UMBRAL = 0.4              # puntaje mínimo (0 a 1) para considerar un candidato
DIFERENCIA_AMBIGUA = 0.3  # si el 1.º y el 2.º se parecen menos que esto, es ambiguo


def buscar_cliente(nombre: str, limite: int = 5, umbral: float = UMBRAL) -> list[dict]:
    """Clientes parecidos al texto, comparando contra el nombre y los apodos."""
    sql = """
        SELECT id, nombre, puntaje FROM (
            SELECT c.id, c.nombre,
                   GREATEST(word_similarity(%(q)s, c.nombre),
                            COALESCE(MAX(word_similarity(%(q)s, a.alias)), 0)) AS puntaje
            FROM clientes c
            LEFT JOIN alias_cliente a ON a.cliente_id = c.id
            WHERE c.activo
            GROUP BY c.id, c.nombre
        ) t
        WHERE puntaje >= %(umbral)s
        ORDER BY puntaje DESC, id
        LIMIT %(limite)s
    """
    with get_conn() as conn:
        filas = conn.execute(
            sql, {"q": nombre, "umbral": umbral, "limite": limite}
        ).fetchall()
    return [
        {"id": f["id"], "nombre": f["nombre"], "puntaje": round(float(f["puntaje"]), 2)}
        for f in filas
    ]


def buscar_producto(texto: str, limite: int = 5, umbral: float = UMBRAL) -> list[dict]:
    """Productos del catálogo parecidos al texto."""
    sql = """
        SELECT id, nombre, precio_ref::float AS precio_ref,
               word_similarity(%(q)s, nombre) AS puntaje
        FROM productos
        WHERE activo AND word_similarity(%(q)s, nombre) >= %(umbral)s
        ORDER BY puntaje DESC, id
        LIMIT %(limite)s
    """
    with get_conn() as conn:
        filas = conn.execute(
            sql, {"q": texto, "umbral": umbral, "limite": limite}
        ).fetchall()
    return [
        {
            "id": f["id"],
            "nombre": f["nombre"],
            "precio_ref": f["precio_ref"],
            "puntaje": round(float(f["puntaje"]), 2),
        }
        for f in filas
    ]


def _decidir(candidatos: list[dict]) -> dict:
    """Regla: sin candidatos -> no_encontrado; uno claramente mejor -> encontrado;
    varios parecidos -> ambiguo (lo decide el tendero)."""
    if not candidatos:
        return {"estado": "no_encontrado", "candidatos": []}
    if len(candidatos) == 1 or (
        candidatos[0]["puntaje"] - candidatos[1]["puntaje"] >= DIFERENCIA_AMBIGUA
    ):
        return {"estado": "encontrado", "elegido": candidatos[0], "candidatos": candidatos}
    return {"estado": "ambiguo", "candidatos": candidatos}


def resolver_cliente(nombre: str) -> dict:
    return _decidir(buscar_cliente(nombre))


def resolver_producto(texto: str) -> dict:
    return _decidir(buscar_producto(texto))