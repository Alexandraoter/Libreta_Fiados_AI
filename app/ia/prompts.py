"""Instrucciones para la IA. No dependen de ningún proveedor."""

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


def construir_prompt(correccion: str | None = None) -> str:
    """Prompt base; si hubo un intento fallido, le agrega los errores para que los corrija."""
    if not correccion:
        return PROMPT
    return (
        PROMPT
        + "\n\nTu respuesta anterior no cumplio el formato. Errores: "
        + f"{correccion}. Corrigelos y responde solo con el JSON."
    )
