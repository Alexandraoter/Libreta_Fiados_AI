import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ia.falso import ESCENARIOS, ProveedorFalso
from app.web.main import app, leer_hoja
from app.web.schemas import validar_hoja

IMG = b"x"
MIME = "image/jpeg"


def test_reintento_manda_correccion():
    p = ProveedorFalso([ESCENARIOS["invalido"], ESCENARIOS["ok"]])
    hoja, intentos = leer_hoja(IMG, MIME, proveedor=p)
    assert intentos == 2
    assert p.llamadas[0] is None
    assert "movimientos.0.tipo" in p.llamadas[1]
    assert len(hoja.movimientos) == 2


def test_dos_respuestas_invalidas_dan_422(monkeypatch):
    monkeypatch.setenv("MAX_INTENTOS", "2")
    p = ProveedorFalso(ESCENARIOS["invalido"])
    with pytest.raises(HTTPException) as exc:
        leer_hoja(IMG, MIME, proveedor=p)
    assert exc.value.status_code == 422
    assert len(p.llamadas) == 2


def test_hoja_vacia_da_422():
    p = ProveedorFalso(ESCENARIOS["vacio"])
    with pytest.raises(HTTPException) as exc:
        leer_hoja(IMG, MIME, proveedor=p)
    assert exc.value.status_code == 422


@pytest.mark.parametrize("escenario,codigo", [("timeout", 504), ("cuota", 429), ("api", 503)])
def test_fallos_del_proveedor_se_traducen_a_http(escenario, codigo):
    p = ProveedorFalso(ESCENARIOS[escenario])
    with pytest.raises(HTTPException) as exc:
        leer_hoja(IMG, MIME, proveedor=p)
    assert exc.value.status_code == codigo


def test_advertencias_de_la_ia_se_conservan():
    texto = (
        '{"movimientos": [{"texto_original": "x", "tipo": "abono", '
        '"cliente": "don pedro", "monto": 5000, "items": [], '
        '"advertencias": ["monto dudoso"]}]}'
    )
    hoja = validar_hoja(texto)
    assert "monto dudoso" in hoja.movimientos[0].advertencias


def test_endpoint_traduce_timeout(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "falso")
    monkeypatch.setenv("FALSO_ESCENARIO", "timeout")
    r = TestClient(app).post(
        "/api/extraer", files={"foto": ("a.jpg", IMG, MIME)}
    )
    assert r.status_code == 504


def test_endpoint_ia_sin_configurar(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "inexistente")
    r = TestClient(app).post(
        "/api/extraer", files={"foto": ("a.jpg", IMG, MIME)}
    )
    assert r.status_code == 503