"""Proveedor falso: simula a la IA sin gastar cuota. Sirve para probar los 3 fallos,
la interfaz y los tests.

Uso manual (sin Gemini):
    PROVEEDOR_IA=falso FALSO_ESCENARIO=timeout  uvicorn app.web.main:app
Escenarios: ok | timeout | cuota | api | invalido | vacio
"""
import json

from .errores import FalloProveedor

JSON_OK = json.dumps({
    "movimientos": [
        {
            "texto_original": "doña rosa 3 arroz x 2800 = 8400",
            "tipo": "fiado", "cliente": "doña rosa", "monto": 8400,
            "items": [{"producto": "arroz", "cantidad": 3, "precio_unitario": 2800}],
            "advertencias": [],
        },
        {
            "texto_original": "don pedro abono 5000",
            "tipo": "abono", "cliente": "don pedro", "monto": 5000,
            "items": [], "advertencias": [],
        },
    ]
})

ESCENARIOS: dict[str, "str | Exception"] = {
    "ok": JSON_OK,
    "vacio": '{"movimientos": []}',
    "invalido": '{"movimientos": [{"tipo": "regalo"}]}',   # no cumple el contrato
    "timeout": FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo."),
    "cuota": FalloProveedor("cuota", "Se agotó el límite de uso de la IA. Espera un minuto e intenta de nuevo."),
    "api": FalloProveedor("api", "No se pudo conectar con la IA. Revisa la clave y vuelve a intentar."),
}


class ProveedorFalso:
    """Devuelve (o lanza) las respuestas en orden; la última se repite."""

    def __init__(self, respuestas: "list[str | Exception] | str | Exception"):
        self.respuestas = respuestas if isinstance(respuestas, list) else [respuestas]
        self.llamadas: list[str | None] = []   # `correccion` recibida en cada llamada

    def leer_hoja(self, img: bytes, mime: str, correccion: str | None = None) -> str:
        self.llamadas.append(correccion)
        i = min(len(self.llamadas) - 1, len(self.respuestas) - 1)
        r = self.respuestas[i]
        if isinstance(r, Exception):
            raise r
        return r
