"""Prueba de extraccion: foto de la libreta -> movimientos estructurados.
 
Uso (desde la carpeta pruebas, con el .venv activo):
    python test_extraccion.py hoja1.jpg
 
La IA PROPONE; este script VALIDA el contrato con Pydantic y revisa
que las sumas cuadren. Nada se guarda en la base de datos aqui.
"""
import os
import sys
from typing import Literal, Optional
 
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
 
load_dotenv()
 
 
# ---------- Contrato de datos (coincide con la BD) ----------
class Item(BaseModel):
    producto: str
    cantidad: float
    precio_unitario: Optional[float] = None
 
 
class Movimiento(BaseModel):
    cliente: Optional[str] = None
    tipo: Literal["venta", "fiado", "abono"]   # igual que el CHECK de la BD
    monto: Optional[float] = None              # None = el cuaderno no trae total
    items: list[Item] = []
    texto_original: str
 
 
class Hoja(BaseModel):
    movimientos: list[Movimiento]
 
 
PROMPT = """Eres un asistente que lee la libreta de fiados de una tienda de barrio en Colombia.
Lee la foto y devuelve SOLO un JSON con exactamente esta forma:
 
{
  "movimientos": [
    {
      "cliente": "nombre tal como esta escrito, o null si no aparece",
      "tipo": "venta" | "fiado" | "abono",
      "monto": 8400,
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
- cantidad: numero. Si no hay precio unitario escrito, usa null.
- Si "items" no aplica (por ejemplo un abono), devuelve una lista vacia.
- NO inventes datos y NO corrijas sumas: copia los montos tal como estan escritos.
- Si no estas seguro de un dato, usa null.
- Una entrada del JSON por cada linea de la hoja que sea un movimiento.
"""
 
 
def revisar_suma(m: Movimiento):
    """Devuelve None si no se puede comprobar, o (cuadra, suma).
    cuadra es None cuando el cuaderno no trae monto."""
    if not m.items or any(i.precio_unitario is None for i in m.items):
        return None
    suma = sum(i.cantidad * i.precio_unitario for i in m.items)
    if m.monto is None:
        return None, suma
    return abs(suma - m.monto) < 0.01, suma
 
 
def mensaje_error(m: Movimiento) -> Optional[str]:
    """Devuelve un mensaje si la anotacion tiene un problema."""
    r = revisar_suma(m)
    cliente = m.cliente or "sin cliente"
 
    if m.monto is None:
        if r is None:
            return (
                f"ERROR EN LA ANOTACION: {cliente} -> falta el monto y no hay "
                f"items para calcularlo. Linea: \"{m.texto_original}\""
            )
        return (
            f"ERROR EN LA ANOTACION: {cliente} -> el cuaderno no trae el total "
            f"(los productos suman {r[1]:,.0f}). Linea: \"{m.texto_original}\""
        )
 
    if r is None or r[0]:
        return None
 
    _, suma = r
    diferencia = m.monto - suma
    return (
        f"ERROR EN LA ANOTACION: {cliente} -> "
        f"los productos suman {suma:,.0f} pero el cuaderno dice {m.monto:,.0f} "
        f"(diferencia de {diferencia:+,.0f}). Linea: \"{m.texto_original}\""
    )
 
 
def pedir_a_gemini(ruta: str) -> str:
    from google import genai
    from google.genai import types
 
    mime = "image/png" if ruta.lower().endswith(".png") else "image/jpeg"
    with open(ruta, "rb") as f:
        img = f.read()
 
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=os.environ["MODEL_NAME"],
        contents=[types.Part.from_bytes(data=img, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    return resp.text
 
 
def validar(texto_json: str) -> Hoja:
    return Hoja.model_validate_json(texto_json)
 
 
def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else "foto.jpg"
    texto = pedir_a_gemini(ruta)
 
    try:
        hoja = validar(texto)
    except ValidationError as e:
        print("La IA devolvio un JSON que NO cumple el contrato:")
        print(e)
        print("--- Respuesta cruda ---")
        print(texto)
        sys.exit(1)
 
    print(hoja.model_dump_json(indent=2))
    print()
    print("=== Revision de sumas ===")
    errores = []
    for m in hoja.movimientos:
        r = revisar_suma(m)
        if m.monto is None:
            estado = "FALTA EL TOTAL"
        elif r is None:
            estado = "sin items para comprobar"
        elif r[0]:
            estado = "OK, cuadra"
        else:
            estado = "NO CUADRA"
        monto_txt = f"{m.monto:.0f}" if m.monto is not None else "sin monto"
        print(f"- {m.cliente} | {m.tipo} | {monto_txt} -> {estado}")
 
        msg = mensaje_error(m)
        if msg:
            errores.append(msg)
 
    if errores:
        print()
        print("!!! HUBO ERRORES AL HACER LA ANOTACION !!!")
        for e in errores:
            print(" *", e)
 
 
if __name__ == "__main__":
    main()