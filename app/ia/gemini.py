"""Implementación del proveedor con Google Gemini. Único archivo que importa `genai`."""
import os
import time

from google import genai
from google.genai import types

from .errores import FalloProveedor
from .prompts import construir_prompt

PAUSA_SATURADA_S = 2   # espera antes de reintentar cuando Gemini está saturado (error 503)


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


def _es_saturada(e: Exception) -> bool:
    """Gemini está sobrecargado (503). Suele durar segundos: vale la pena reintentar una vez."""
    texto = (type(e).__name__ + " " + str(e)).lower()
    return "503" in texto or "unavailable" in texto or "high demand" in texto


class GeminiProveedor:
    def __init__(self, api_key: str | None, modelo: str, timeout_s: int, max_tokens: int):
        self.modelo = modelo
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.api_key = api_key
        # Tokens acumulados de todas las llamadas de este objeto (lo usa eval/ para el costo)
        self.uso = {"llamadas": 0, "entrada": 0, "salida": 0, "total": 0}

    def leer_hoja(self, img: bytes, mime: str, correccion: str | None = None) -> str:
        # Opcional: MINIMAL, LOW, MEDIUM o HIGH. Vacío = el comportamiento por defecto del modelo.
        nivel = os.getenv("THINKING_LEVEL", "").strip().upper()
        respuesta = None
        for intento in range(2):
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
                        thinking_config=types.ThinkingConfig(thinking_level=nivel) if nivel else None,
                    ),
                )
                break
            except Exception as e:
                print("Fallo de Gemini:", type(e).__name__, e)
                if _es_timeout(e):
                    raise FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo.")
                if _es_cuota(e):
                    raise FalloProveedor(
                        "cuota",
                        "Se agotó el límite de uso de la IA. Espera un minuto e intenta de nuevo.",
                    )
                if _es_saturada(e):
                    if intento == 0:
                        time.sleep(PAUSA_SATURADA_S)
                        continue
                    raise FalloProveedor(
                        "api", "La IA está saturada en este momento. Intenta de nuevo en unos segundos."
                    )
                raise FalloProveedor(
                    "api", "No se pudo conectar con la IA. Revisa la clave y vuelve a intentar."
                )

        u = respuesta.usage_metadata
        self.uso["llamadas"] += 1
        if u:
            entrada = u.prompt_token_count or 0
            salida = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
            self.uso["entrada"] += entrada
            self.uso["salida"] += salida
            self.uso["total"] += u.total_token_count or (entrada + salida)

        texto = (respuesta.text or "").strip()
        if not texto:
            raise FalloProveedor("api", "La IA no devolvió respuesta. Intenta de nuevo.")
        return texto