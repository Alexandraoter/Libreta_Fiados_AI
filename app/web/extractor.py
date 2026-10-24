"""Llama a Gemini para leer una foto de la libreta. Devuelve el JSON como texto."""
import os
import time

from dotenv import load_dotenv

load_dotenv()


class ErrorIA(Exception):
    """Fallo al hablar con Gemini. .estado_http es el código HTTP que verá el cliente."""

    def __init__(self, mensaje: str, estado_http: int = 502):
        super().__init__(mensaje)
        self.estado_http = estado_http


MAX_INTENTOS = int(os.environ.get("MAX_INTENTOS", "3"))
TIMEOUT_SEGUNDOS = int(os.environ.get("TIMEOUT_SEGUNDOS", "30"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8192"))

PROMPT = """Eres un asistente que lee la libreta de fiados de una tienda de barrio en Colombia.
Lee la foto y devuelve SOLO un JSON con exactamente esta forma:

{
  "movimientos": [
    {
      "cliente": "nombre tal como esta escrito, o null si no aparece",
      "tipo": "venta" | "fiado" | "abono",
      "monto": 8400,
      "fecha": "YYYY-MM-DD o null",
      "items": [
        {"producto": "arroz", "cantidad": 3, "precio_unitario": 2800}
      ],
      "texto_original": "la linea tal como aparece en el cuaderno"
    }
  ]
}

Reglas:
- tipo "fiado": venta a credito. tipo "abono": el cliente paga parte de su deuda.
  tipo "venta": pago de contado.
- monto: numero en pesos, sin puntos, comas ni simbolo (8.400 se escribe 8400).
  Si la linea NO trae un total escrito, usa null. NO lo calcules tu.
- fecha: solo si esta escrita con claridad; si no, null.
- cantidad: numero. Si no hay precio unitario escrito, usa null.
- Si "items" no aplica (por ejemplo un abono), devuelve una lista vacia.
- Escribe el cliente y los productos tal como aparecen (ej: "Don Pedro"); no completes apellidos.
- NO inventes datos y NO corrijas sumas: copia los montos tal como estan escritos.
- Si no estas seguro de un dato, usa null.
- Una entrada del JSON por cada linea de la hoja que sea un movimiento.
"""


def extraer_texto(img_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    from google import genai
    from google.genai import errors, types

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=TIMEOUT_SEGUNDOS * 1000),  # en milisegundos
    )
    modelo = os.environ["MODEL_NAME"]
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0,
        max_output_tokens=MAX_TOKENS,
    )
    contenido = [types.Part.from_bytes(data=img_bytes, mime_type=mime_type), PROMPT]

    for intento in range(1, MAX_INTENTOS + 1):
        try:
            resp = client.models.generate_content(
                model=modelo, contents=contenido, config=config
            )
            if resp.candidates and "MAX_TOKENS" in str(resp.candidates[0].finish_reason):
                raise ErrorIA(
                    "La hoja es demasiado larga para una sola lectura. "
                    "Fotografía menos líneas.", 422)
            if not resp.text:
                raise ErrorIA("Gemini devolvió una respuesta vacía. Intenta con otra foto.", 502)
            return resp.text
        except ErrorIA:
            raise
        except errors.ClientError as e:  # error 4xx: repetir no sirve
            if e.code == 429:
                raise ErrorIA(
                    "Se agotó la cuota de la IA. Espera un minuto e intenta de nuevo.", 429)
            if e.code in (401, 403) or "API key" in str(e):
                raise ErrorIA(
                    "La llave de Gemini no es válida. Revisa GEMINI_API_KEY en el .env.", 502)
            raise ErrorIA(f"Gemini rechazó la solicitud (código {e.code}).", 502)
        except Exception as e:  # error 5xx, tiempo agotado o red: se reintenta
            print(f"Intento {intento}/{MAX_INTENTOS} falló: {e!r}")
            if intento < MAX_INTENTOS:
                time.sleep(2 * intento)
    raise ErrorIA("Gemini no respondió a tiempo. Intenta de nuevo en un minuto.", 504)