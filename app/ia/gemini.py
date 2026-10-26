"""Implementación del proveedor con Google Gemini. Único archivo que importa `genai`."""
from google import genai
from google.genai import types

from .errores import FalloProveedor
from .prompts import construir_prompt


def _es_timeout(e: Exception) -> bool:
    nombre = type(e).__name__.lower()
    texto = str(e).lower()
    return (
        isinstance(e, TimeoutError)
        or "timeout" in nombre
        or "timed out" in texto
        or "deadline" in texto
    )


def _es_cuota(e: Exception) -> bool:
    texto = (type(e).__name__ + " " + str(e)).lower()
    return (
        "429" in texto
        or "resource_exhausted" in texto
        or "quota" in texto
        or "rate limit" in texto
    )


class GeminiProveedor:
    def __init__(self, api_key: str | None, modelo: str, timeout_s: int, max_tokens: int):
        self.modelo = modelo
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.api_key = api_key

    def leer_hoja(self, img: bytes, mime: str, correccion: str | None = None) -> str:
        try:
            client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=self.timeout_s * 1000),
            )
            respuesta = client.models.generate_content(
                model=self.modelo,
                contents=[types.Part.from_bytes(data=img, mime_type=mime), construir_prompt(correccion)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                    max_output_tokens=self.max_tokens,
                ),
            )
        except Exception as e:
            print("Fallo de Gemini:", type(e).__name__, e)
            if _es_timeout(e):
                raise FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo.")
            if _es_cuota(e):
                raise FalloProveedor(
                    "cuota",
                    "Se agotó el límite de uso de la IA. Espera un minuto e intenta de nuevo.",
                )
            raise FalloProveedor(
                "api", "No se pudo conectar con la IA. Revisa la clave y vuelve a intentar."
            )

        texto = (respuesta.text or "").strip()
        if not texto:
            raise FalloProveedor("api", "La IA no devolvió respuesta. Intenta de nuevo.")
        return texto
