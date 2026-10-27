"""Pruebas del proveedor Gemini con un cliente falso (no llaman a la API real)."""
from types import SimpleNamespace

import pytest

from app.ia import gemini
from app.ia.errores import FalloProveedor


def _respuesta(texto='{"movimientos": []}'):
    uso = SimpleNamespace(
        prompt_token_count=1000, candidates_token_count=200,
        thoughts_token_count=300, total_token_count=1500,
    )
    return SimpleNamespace(text=texto, usage_metadata=uso)


def _cliente_falso(resultados, llamadas):
    """Cada llamada consume el siguiente resultado: una excepción se lanza, lo demás se devuelve."""
    class Modelos:
        def generate_content(self, **kwargs):
            r = resultados[min(len(llamadas), len(resultados) - 1)]
            llamadas.append(kwargs)
            if isinstance(r, Exception):
                raise r
            return r

    class Cliente:
        def __init__(self, **kwargs):
            self.models = Modelos()

    return Cliente


def _proveedor(monkeypatch, resultados):
    llamadas = []
    monkeypatch.setattr(gemini.genai, "Client", _cliente_falso(resultados, llamadas))
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)   # sin esperas reales
    return gemini.GeminiProveedor("clave", "modelo", 30, 8192), llamadas


def test_devuelve_el_texto_y_suma_tokens(monkeypatch):
    p, llamadas = _proveedor(monkeypatch, [_respuesta()])
    assert p.leer_hoja(b"x", "image/jpeg") == '{"movimientos": []}'
    assert p.uso == {"llamadas": 1, "entrada": 1000, "salida": 500, "total": 1500}


def test_reintenta_una_vez_si_gemini_esta_saturado(monkeypatch):
    saturado = Exception("503 UNAVAILABLE. This model is currently experiencing high demand.")
    p, llamadas = _proveedor(monkeypatch, [saturado, _respuesta()])
    assert p.leer_hoja(b"x", "image/jpeg")
    assert len(llamadas) == 2


def test_saturado_dos_veces_da_mensaje_claro(monkeypatch):
    saturado = Exception("503 UNAVAILABLE high demand")
    p, llamadas = _proveedor(monkeypatch, [saturado])
    with pytest.raises(FalloProveedor) as exc:
        p.leer_hoja(b"x", "image/jpeg")
    assert exc.value.codigo == "api"
    assert "saturada" in exc.value.mensaje
    assert len(llamadas) == 2


@pytest.mark.parametrize("error,codigo", [
    (TimeoutError("lento"), "timeout"),
    (Exception("504 DEADLINE_EXCEEDED"), "timeout"),
    (Exception("429 RESOURCE_EXHAUSTED"), "cuota"),
    (Exception("connection refused"), "api"),
])
def test_los_demas_errores_no_se_reintentan(monkeypatch, error, codigo):
    p, llamadas = _proveedor(monkeypatch, [error])
    with pytest.raises(FalloProveedor) as exc:
        p.leer_hoja(b"x", "image/jpeg")
    assert exc.value.codigo == codigo
    assert len(llamadas) == 1


def test_respuesta_vacia_da_fallo(monkeypatch):
    p, _ = _proveedor(monkeypatch, [_respuesta("")])
    with pytest.raises(FalloProveedor) as exc:
        p.leer_hoja(b"x", "image/jpeg")
    assert exc.value.codigo == "api"