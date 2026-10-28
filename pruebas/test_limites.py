"""Pruebas de los límites (clave, tiempo total, tokens acumulados) y de las trazas hacia la pantalla."""
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ia import FalloProveedor, obtener_proveedor
from app.ia.falso import ESCENARIOS
from app.ia.presupuesto import Presupuesto
from app.web import main
from app.web.main import app, leer_hoja

IMG, MIME = b"x", "image/jpeg"
JSON_INVALIDO = ESCENARIOS["invalido"]


class ProveedorLento:
    """Simula una IA que tarda, gasta tokens y responde algo inválido (para forzar reintentos)."""

    def __init__(self, demora_s=0.0, tokens=0):
        self.demora_s, self.tokens, self.n = demora_s, tokens, 0

    def leer_hoja(self, img, mime, correccion=None, trazas=None, presupuesto=None):
        self.n += 1
        time.sleep(self.demora_s)
        presupuesto.registrar(self.tokens)
        return JSON_INVALIDO


# ---------- Punto 1: GEMINI_API_KEY ----------
@pytest.mark.parametrize("valor", ["", "   "])
def test_clave_vacia_falla_al_crear_el_proveedor(monkeypatch, valor):
    monkeypatch.setenv("PROVEEDOR_IA", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", valor)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        obtener_proveedor()


def test_clave_ausente_falla_al_crear_el_proveedor(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        obtener_proveedor()


def test_con_clave_se_crea_el_proveedor_con_sus_limites(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "  abc  ")
    monkeypatch.setenv("MAX_ITERACIONES", "3")
    p = obtener_proveedor()
    assert p.api_key == "abc" and p.max_iteraciones == 3


def test_thinking_level_invalido_se_rechaza(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    monkeypatch.setenv("THINKING_LEVEL", "RAPIDO")
    with pytest.raises(ValueError, match="THINKING_LEVEL"):
        obtener_proveedor()


def test_endpoint_sin_clave_da_503(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    r = TestClient(app).post("/api/extraer", files={"foto": ("a.jpg", IMG, MIME)})
    assert r.status_code == 503 and "no está configurada" in r.json()["detail"]


def test_el_falso_no_necesita_clave(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "falso")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert obtener_proveedor() is not None


# ---------- Punto 2: tiempo total entre reintentos ----------
def test_tiempo_total_corta_los_reintentos(monkeypatch):
    monkeypatch.setenv("MAX_INTENTOS", "5")
    monkeypatch.setenv("TIMEOUT_TOTAL_SEGUNDOS", "0.15")
    p = ProveedorLento(demora_s=0.1)
    t0 = time.perf_counter()
    with pytest.raises(HTTPException) as exc:
        leer_hoja(IMG, MIME, proveedor=p)
    assert exc.value.status_code == 504
    assert p.n == 2                                   # 5 intentos permitidos, pero se acabó el tiempo
    assert time.perf_counter() - t0 < 0.5


def test_presupuesto_sin_tope_de_tiempo():
    pres = Presupuesto(0, 0)
    pres.registrar(10 ** 9)
    pres.verificar()                                  # 0 = sin tope: no lanza


# ---------- Punto 3: tokens acumulados entre reintentos ----------
def test_tokens_acumulados_cortan_los_reintentos(monkeypatch):
    monkeypatch.setenv("MAX_INTENTOS", "5")
    monkeypatch.setenv("MAX_TOKENS_ACUMULADOS", "2500")
    p = ProveedorLento(tokens=1000)
    with pytest.raises(HTTPException) as exc:
        leer_hoja(IMG, MIME, proveedor=p)
    assert exc.value.status_code == 422 and "más IA de la permitida" in exc.value.detail
    assert p.n == 3                                   # 1000 + 1000 + 1000 > 2500: no hay 4.º intento


def test_variable_de_limite_mal_escrita_da_503(monkeypatch):
    monkeypatch.setenv("MAX_TOKENS_ACUMULADOS", "mucho")
    with pytest.raises(HTTPException) as exc:
        leer_hoja(IMG, MIME, proveedor=ProveedorLento())
    assert exc.value.status_code == 503


# ---------- Punto 12: trazas hacia la pantalla ----------
@pytest.mark.parametrize("escenario,codigo", [("timeout", 504), ("cuota", 429), ("api", 503), ("vacio", 422)])
def test_los_fallos_devuelven_trazas(monkeypatch, escenario, codigo):
    monkeypatch.setenv("PROVEEDOR_IA", "falso")
    monkeypatch.setenv("FALSO_ESCENARIO", escenario)
    r = TestClient(app).post("/api/extraer", files={"foto": ("hoja.jpg", IMG, MIME)})
    cuerpo = r.json()
    assert r.status_code == codigo and isinstance(cuerpo["detail"], str)
    assert cuerpo["trazas"][0]["estado"] == "error" and cuerpo["trazas"][0]["entrada"] == "hoja.jpg"
    assert str(codigo) in cuerpo["trazas"][0]["detalle"]


def test_respuesta_invalida_deja_traza_de_cada_intento(monkeypatch):
    monkeypatch.setenv("PROVEEDOR_IA", "falso")
    monkeypatch.setenv("FALSO_ESCENARIO", "invalido")
    monkeypatch.setenv("MAX_INTENTOS", "2")
    r = TestClient(app).post("/api/extraer", files={"foto": ("a.jpg", IMG, MIME)})
    estados = [t["estado"] for t in r.json()["trazas"]]
    assert r.status_code == 422 and estados == ["error", "invalido", "invalido"]


def test_exito_une_lectura_agente_y_bd(monkeypatch):
    class ConAgente:
        def leer_hoja(self, img, mime, correccion=None, trazas=None, presupuesto=None):
            trazas.append({"herramienta": "buscar_cliente (agente)", "entrada": "rosita",
                           "estado": "encontrado", "detalle": "candidatos: Rosa Martínez", "ms": 3})
            return ESCENARIOS["ok"]

    sin_bd = {"estado": "no_encontrado", "candidatos": []}
    monkeypatch.setattr(main, "obtener_proveedor", lambda: ConAgente())
    monkeypatch.setattr(main, "resolver_cliente", lambda n: sin_bd)
    monkeypatch.setattr(main, "resolver_producto", lambda n: sin_bd)
    r = TestClient(app).post("/api/extraer", files={"foto": ("a.jpg", IMG, MIME)})
    nombres = [t["herramienta"] for t in r.json()["trazas"]]
    assert r.status_code == 200
    assert nombres[:2] == ["leer_hoja (Gemini)", "buscar_cliente (agente)"]      # lectura, luego el agente
    assert nombres[2:] == ["buscar_cliente", "buscar_producto", "buscar_cliente"]  # y al final la BD (doña rosa, arroz, don pedro)
