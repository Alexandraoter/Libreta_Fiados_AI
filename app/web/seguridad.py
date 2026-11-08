"""Seguridad de la capa web. Todo se activa por variables de entorno:
vacías = el comportamiento de siempre."""
import hmac
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_visitas: dict[str, deque] = defaultdict(deque)


def verificar_clave(request: Request):
    """Si APP_API_KEY está definida, exige el encabezado X-API-Key."""
    esperada = os.getenv("APP_API_KEY", "")
    if not esperada:
        return
    recibida = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(recibida.encode(), esperada.encode()):
        raise HTTPException(status_code=401, detail="Falta la clave de acceso o es incorrecta.")


def limitar_extracciones(request: Request):
    """Máximo LIMITE_EXTRAER_POR_MIN fotos por minuto y por IP (0 = sin límite)."""
    maximo = int(os.getenv("LIMITE_EXTRAER_POR_MIN", "0"))
    if maximo <= 0:
        return
    ip = request.client.host if request.client else "?"
    ahora = time.monotonic()
    cola = _visitas[ip]
    while cola and ahora - cola[0] > 60:
        cola.popleft()
    if len(cola) >= maximo:
        raise HTTPException(status_code=429, detail="Demasiadas fotos seguidas. Espera un minuto.")
    cola.append(ahora)


def tipo_real_imagen(datos: bytes) -> str | None:
    """Mira los primeros bytes (la 'firma'), no lo que declara el cliente."""
    if datos.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


async def cabeceras_seguras(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    return respuesta