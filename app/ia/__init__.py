"""Capa de IA: el resto de la app solo usa `obtener_proveedor()`."""
import os

from dotenv import load_dotenv

from .errores import FalloProveedor
from .proveedor import ProveedorIA

load_dotenv()

__all__ = ["obtener_proveedor", "FalloProveedor", "ProveedorIA"]


def obtener_proveedor() -> ProveedorIA:
    """Elige el proveedor según PROVEEDOR_IA (por defecto 'gemini')."""
    nombre = os.getenv("PROVEEDOR_IA", "gemini").lower()

    if nombre == "gemini":
        from .gemini import GeminiProveedor   # import perezoso: solo si se usa

        return GeminiProveedor(
            api_key=os.getenv("GEMINI_API_KEY"),
            modelo=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
            timeout_s=int(os.getenv("TIMEOUT_SEGUNDOS", "30")),
            max_tokens=int(os.getenv("MAX_TOKENS", "8192")),
        )

    if nombre == "falso":
        from .falso import ESCENARIOS, ProveedorFalso

        escenario = os.getenv("FALSO_ESCENARIO", "ok")
        if escenario not in ESCENARIOS:
            raise ValueError(f"FALSO_ESCENARIO desconocido: {escenario}")
        return ProveedorFalso(ESCENARIOS[escenario])

    raise ValueError(f"PROVEEDOR_IA desconocido: {nombre!r} (usa 'gemini' o 'falso')")
