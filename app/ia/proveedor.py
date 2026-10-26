"""Interfaz que debe cumplir cualquier proveedor de IA.

El resto de la app solo conoce esta interfaz. Para cambiar de proveedor se
escribe una clase nueva con el mismo método y se registra en app/ia/__init__.py.
"""
from typing import Protocol


class ProveedorIA(Protocol):
    def leer_hoja(self, img: bytes, mime: str, correccion: str | None = None) -> str:
        """Lee la foto y devuelve el JSON CRUDO (texto) que propone la IA.

        No valida el contenido: eso lo hace app/web/schemas.py.
        `correccion` trae los errores del intento anterior para que la IA los arregle.

        Lanza FalloProveedor (timeout | cuota | api) si algo falla.
        """
        ...
