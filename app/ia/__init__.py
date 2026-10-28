"""Capa de IA: el resto de la app solo usa `obtener_proveedor()`."""
import os

from dotenv import load_dotenv

from .errores import FalloProveedor
from .proveedor import ProveedorIA

load_dotenv()

__all__ = ["obtener_proveedor", "FalloProveedor", "ProveedorIA"]

NIVELES_THINKING = {"", "MINIMAL", "LOW", "MEDIUM", "HIGH"}


def obtener_proveedor() -> ProveedorIA:
    """Elige el proveedor según PROVEEDOR_IA (por defecto 'gemini').

    Lanza ValueError si la configuración es inválida; main.py lo traduce a un 503 claro.
    """
    nombre = os.getenv("PROVEEDOR_IA", "gemini").lower()

    if nombre == "gemini":
        # Falla AQUÍ, al crear el proveedor, y no en la primera llamada a la API
        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY está vacía o no está definida. Pégala en .env "
                "(se obtiene en https://aistudio.google.com/apikey) o usa PROVEEDOR_IA=falso para probar sin Gemini."
            )
        nivel = os.getenv("THINKING_LEVEL", "").strip().upper()
        if nivel not in NIVELES_THINKING:
            raise ValueError(f"THINKING_LEVEL inválido: {nivel!r} (usa MINIMAL, LOW, MEDIUM, HIGH o déjalo vacío)")

        from .gemini import GeminiProveedor   # import perezoso: solo si se usa

        return GeminiProveedor(
            api_key=api_key,
            modelo=os.getenv("MODEL_NAME", "gemini-2.5-flash"),
            timeout_s=int(os.getenv("TIMEOUT_SEGUNDOS", "30")),
            max_tokens=int(os.getenv("MAX_TOKENS", "8192")),
            max_iteraciones=int(os.getenv("MAX_ITERACIONES", "4")),
        )

    if nombre == "falso":
        from .falso import ESCENARIOS, ProveedorFalso

        escenario = os.getenv("FALSO_ESCENARIO", "ok")
        if escenario not in ESCENARIOS:
            raise ValueError(f"FALSO_ESCENARIO desconocido: {escenario}")
        return ProveedorFalso(ESCENARIOS[escenario])

    raise ValueError(f"PROVEEDOR_IA desconocido: {nombre!r} (usa 'gemini' o 'falso')")
