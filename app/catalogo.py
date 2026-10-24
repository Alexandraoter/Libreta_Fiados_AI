"""Altas de clientes y productos nuevos.

SIEMPRE ocurren por decisión del tendero: la IA nunca crea registros.
Si el nombre se parece a uno existente, se rechaza y se devuelven los
parecidos, para que el tendero confirme que es otra persona o producto."""
from decimal import Decimal, InvalidOperation
from typing import Optional

import psycopg

from app.db import get_conn
from app.herramientas import buscar_cliente, buscar_producto

PUNTAJE_PARECIDO = 0.8  # desde aquí un nombre se considera "casi igual" a otro


class RegistroInvalido(Exception):
    """Alta rechazada. .errores trae los motivos y .parecidos los registros similares."""

    def __init__(self, errores: list[str], parecidos: Optional[list[dict]] = None):
        super().__init__("; ".join(errores))
        self.errores = errores
        self.parecidos = parecidos or []


def _limpiar(texto: Optional[str]) -> str:
    """Quita espacios sobrantes: '  doña   rosa ' -> 'doña rosa'."""
    return " ".join((texto or "").split())


def _con_conexion(conn, funcion, *args):
    """Usa la conexión recibida (sin confirmar) o abre una propia y confirma."""
    if conn is not None:
        return funcion(conn, *args)
    with get_conn() as propia:
        return funcion(propia, *args)


# ---------- Clientes ----------
def _alta_cliente(conn, nombre, telefono, alias):
    fila = conn.execute(
        "INSERT INTO clientes (nombre, telefono) VALUES (%s, %s) RETURNING id, nombre",
        (nombre, telefono),
    ).fetchone()
    for a in alias:
        conn.execute(
            "INSERT INTO alias_cliente (cliente_id, alias) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (fila["id"], a),
        )
    return {"id": fila["id"], "nombre": fila["nombre"], "alias": alias}


def crear_cliente(nombre, telefono=None, alias=None, confirmar_duplicado=False, conn=None):
    nombre = _limpiar(nombre)
    if len(nombre) < 2:
        raise RegistroInvalido(["El nombre del cliente es obligatorio."])

    parecidos = [c for c in buscar_cliente(nombre) if c["puntaje"] >= PUNTAJE_PARECIDO]
    if parecidos and not confirmar_duplicado:
        raise RegistroInvalido(
            [f'Ya hay clientes parecidos a "{nombre}". ¿Es la misma persona?'], parecidos
        )

    lista_alias = [a for a in (_limpiar(x) for x in (alias or [])) if a]
    return _con_conexion(conn, _alta_cliente, nombre, _limpiar(telefono) or None, lista_alias)


# ---------- Apodos ----------
def _alta_alias(conn, cliente_id, alias):
    c = conn.execute("SELECT activo FROM clientes WHERE id = %s", (cliente_id,)).fetchone()
    if c is None or not c["activo"]:
        raise RegistroInvalido([f"El cliente {cliente_id} no existe o está inactivo."])
    conn.execute(
        "INSERT INTO alias_cliente (cliente_id, alias) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (cliente_id, alias),
    )
    return {"cliente_id": cliente_id, "alias": alias}


def agregar_alias(cliente_id, alias, conn=None):
    """El tendero enseña un apodo: 'Rosi' -> cliente 1."""
    alias = _limpiar(alias)
    if len(alias) < 2:
        raise RegistroInvalido(["El apodo es obligatorio."])
    return _con_conexion(conn, _alta_alias, cliente_id, alias)


# ---------- Productos ----------
def _alta_producto(conn, nombre, precio):
    try:
        return conn.execute(
            "INSERT INTO productos (nombre, precio_ref) VALUES (%s, %s) "
            "RETURNING id, nombre, precio_ref::float AS precio_ref",
            (nombre, precio),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise RegistroInvalido([f'Ya existe un producto llamado "{nombre}".'])


def crear_producto(nombre, precio_ref, confirmar_duplicado=False, conn=None):
    nombre = _limpiar(nombre)
    errores = []
    if len(nombre) < 2:
        errores.append("El nombre del producto es obligatorio.")
    try:
        precio = Decimal(str(precio_ref))
    except (InvalidOperation, ValueError):
        precio = None
    if precio is None or not precio.is_finite() or precio <= 0:
        errores.append("El precio debe ser un número mayor que cero.")
    if errores:
        raise RegistroInvalido(errores)

    parecidos = [p for p in buscar_producto(nombre) if p["puntaje"] >= PUNTAJE_PARECIDO]
    if parecidos and not confirmar_duplicado:
        raise RegistroInvalido(
            [f'Ya hay productos parecidos a "{nombre}". ¿Es el mismo?'], parecidos
        )
    return _con_conexion(conn, _alta_producto, nombre, precio)