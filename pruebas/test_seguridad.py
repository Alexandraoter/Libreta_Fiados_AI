from fastapi.testclient import TestClient

from app.web.main import app
from app.web.seguridad import tipo_real_imagen


def test_firma_de_imagen():
    assert tipo_real_imagen(b"\xff\xd8\xff\xe0abc") == "image/jpeg"
    assert tipo_real_imagen(b"\x89PNG\r\n\x1a\nabc") == "image/png"
    assert tipo_real_imagen(b"<?php echo 1; ?>") is None


def test_clave_incorrecta_da_401(monkeypatch):
    monkeypatch.setenv("APP_API_KEY", "secreta")
    cliente = TestClient(app)
    assert cliente.get("/api/catalogo").status_code == 401
    assert cliente.get("/api/catalogo", headers={"X-API-Key": "mala"}).status_code == 401


def test_archivo_falso_disfrazado_de_jpg(monkeypatch):
    monkeypatch.delenv("APP_API_KEY", raising=False)
    cliente = TestClient(app)
    r = cliente.post("/api/extraer", files={"foto": ("x.jpg", b"no soy una imagen", "image/jpeg")})
    assert r.status_code == 400