"""Interfaz que debe cumplir cualquier proveedor de IA.

El resto de la app solo conoce esta interfaz. Para cambiar de proveedor se
escribe una clase nueva con el mismo método y se registra en app/ia/__init__.py.
"""
from typing import Protocol


class ProveedorIA(Protocol):
    def leer_hoja(
        self, img: bytes, mime: str, correccion: str | None = None,
        trazas: list | None = None, presupuesto=None,
    ) -> str:
        """Lee la foto y devuelve el JSON CRUDO (texto) que propone la IA.

        No valida el contenido: eso lo hace app/web/schemas.py.
        `correccion` trae los errores del intento anterior para que la IA los arregle.
        `trazas` (opcional): lista a la que el proveedor AGREGA una traza por cada herramienta
        que use; main.py la devuelve a la pantalla.
        `presupuesto` (opcional): app.ia.presupuesto.Presupuesto con el tiempo y los tokens que
        quedan para toda la lectura; el proveedor suma ahí los tokens que gasta.

        Lanza FalloProveedor (timeout | cuota | tokens | api) si algo falla.
        """
        ...
