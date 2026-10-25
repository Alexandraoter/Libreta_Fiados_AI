import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
TIMEOUT_SEGUNDOS = int(os.getenv("TIMEOUT_SEGUNDOS", "30"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "8192"))


class FalloProveedor(Exception):
    """Fallo al llamar a la IA. codigo: 'timeout' o 'api'."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


PROMPT = """Eres un asistente que lee fotos de la libreta de fiados de una tienda de barrio en Colombia.
La letra es manuscrita. Extrae TODOS los movimientos que aparezcan.

Responde SOLO con un JSON valido (sin texto extra, sin ```), con esta forma exacta:

{
  "movimientos": [
    {
      "texto_original": "lo que dice la libreta en esa linea",
      "tipo": "fiado" | "abono" | "venta",
      "cliente": "nombre tal como aparece, o null",
      "monto": numero,
      "items": [
        {"producto": "texto del producto", "cantidad": numero, "precio_unitario": numero}
      ],
      "advertencias": []
    }
  ]
}

Reglas:
- "fiado": el cliente se lleva productos sin pagar. Lleva cliente e items.
- "abono": el cliente paga parte de su deuda. Lleva cliente, monto y items vacio [].
- "venta": venta de contado, normalmente sin cliente (cliente null).
- Los montos son pesos colombianos, como numeros sin puntos ni simbolos ($2.500 -> 2500).
- Si no hay precio unitario legible, pon null en precio_unitario.
- NO inventes datos. Si algo es ilegible o dudoso, dejalo como null y explica el motivo
  en "advertencias" (lista de textos cortos).
- Copia los nombres de clientes y productos tal como estan escritos, no los corrijas.
- Si la imagen no tiene movimientos, responde {"movimientos": []}.
"""


def _es_timeout(e: Exception) -> bool:
    nombre = type(e).__name__.lower()
    texto = str(e).lower()
    return (
        isinstance(e, TimeoutError)
        or "timeout" in nombre
        or "timed out" in texto
        or "deadline" in texto
    )


def extraer_texto(img: bytes, mime: str, correccion: str | None = None) -> str:
    """Envia la foto a Gemini y devuelve el texto JSON crudo.
    Lanza FalloProveedor si la IA tarda demasiado o la API falla.
    `correccion` trae los errores del intento anterior para que la IA los arregle."""
    prompt = PROMPT
    if correccion:
        prompt += (
            "\n\nTu respuesta anterior no cumplio el formato. Errores: "
            f"{correccion}. Corrigelos y responde solo con el JSON."
        )

    try:
        client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=TIMEOUT_SEGUNDOS * 1000),
        )
        respuesta = client.models.generate_content(
            model=MODEL_NAME,
            contents=[types.Part.from_bytes(data=img, mime_type=mime), prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
                max_output_tokens=MAX_TOKENS,
            ),
        )
    except Exception as e:
        print("Fallo de Gemini:", type(e).__name__, e)
        if _es_timeout(e):
            raise FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo.")
        raise FalloProveedor(
            "api", "No se pudo conectar con la IA. Revisa la clave y vuelve a intentar."
        )

    texto = (respuesta.text or "").strip()
    if not texto:
        raise FalloProveedor("api", "La IA no devolvió respuesta. Intenta de nuevo.")
    return texto
    