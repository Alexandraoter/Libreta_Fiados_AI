"""Llama a Gemini para leer una foto de la libreta. Devuelve el JSON como texto."""
import os
import time

from dotenv import load_dotenv

load_dotenv()

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

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    for intento in range(4):
        try:
            resp = client.models.generate_content(
                model=os.environ["MODEL_NAME"],
                contents=[types.Part.from_bytes(data=img_bytes, mime_type=mime_type), PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0,
                ),
            )
            return resp.text
        except errors.ServerError:
            time.sleep(2 ** intento * 5)
    raise RuntimeError("Gemini no respondio tras 4 intentos. Intenta de nuevo en un minuto.")
    