import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()  # lee el archivo .env y carga las variables

api_key = os.environ["GEMINI_API_KEY"]
model = os.environ["MODEL_NAME"]

client = genai.Client(api_key=api_key)

with open("foto.jpg", "rb") as f:
    img = f.read()

resp = client.models.generate_content(
    model=model,
    contents=[
        types.Part.from_bytes(data=img, mime_type="image/jpeg"),
        "Extrae los datos de esta foto y devuélvelos como JSON.",
    ],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0,
    ),
)
print(resp.text)