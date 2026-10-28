"""Pruebas del bucle del agente con un cliente Gemini falso (no llaman a la API ni a la BD)."""
import pytest
from google.genai import types

from app.ia import gemini, herramientas_ia
from app.ia.errores import FalloProveedor
from app.ia.presupuesto import Presupuesto

JSON_OK = '{"movimientos": [{"texto_original": "x", "tipo": "abono", "cliente": "rosita", "monto": 5000}]}'


# ---------- Respuestas y cliente falsos (objetos reales del SDK) ----------
def _uso(total=1000):
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=total - 200, candidates_token_count=150,
        thoughts_token_count=50, total_token_count=total,
    )


def texto(t, total=1000):
    c = types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=t)]))
    return types.GenerateContentResponse(candidates=[c], usage_metadata=_uso(total))


def pide(*llamadas, total=1000):
    """Respuesta del modelo pidiendo herramientas: ("buscar_cliente", {"nombre": "rosita"}), ..."""
    partes = [types.Part.from_function_call(name=n, args=a) for n, a in llamadas]
    c = types.Candidate(content=types.Content(role="model", parts=partes))
    return types.GenerateContentResponse(candidates=[c], usage_metadata=_uso(total))


class Fake:
    """Cada llamada consume la siguiente respuesta (la última se repite) y guarda lo recibido."""

    def __init__(self, respuestas):
        self.respuestas, self.llamadas, self.timeouts = respuestas, [], []

    def instalar(self, monkeypatch):
        fake = self

        class Modelos:
            def generate_content(self, **kwargs):
                r = fake.respuestas[min(len(fake.llamadas), len(fake.respuestas) - 1)]
                fake.llamadas.append(kwargs)
                if isinstance(r, Exception):
                    raise r
                return r

        class Cliente:
            def __init__(self, **kwargs):
                fake.timeouts.append(kwargs["http_options"].timeout)
                self.models = Modelos()

        monkeypatch.setattr(gemini.genai, "Client", Cliente)
        monkeypatch.setattr(gemini.time, "sleep", lambda s: None)


def herramientas_falsas():
    cliente = {"estado": "encontrado", "candidatos": [{"nombre": "Rosa Martínez", "puntaje": 1.0}]}
    producto = {"estado": "no_encontrado", "candidatos": []}
    return {"buscar_cliente": lambda a: cliente, "buscar_producto": lambda a: producto}


def proveedor(monkeypatch, respuestas, **kw):
    fake = Fake(respuestas)
    fake.instalar(monkeypatch)
    kw.setdefault("herramientas", herramientas_falsas())
    return gemini.GeminiProveedor("clave", "modelo", 30, 8192, **kw), fake


def presupuesto(**kw):
    return Presupuesto(kw.get("tiempo", 60), kw.get("tokens", 50000), reloj=kw.get("reloj", lambda: 0.0))


# ---------- Declaraciones (punto 9) ----------
def test_declaraciones_son_validas_para_gemini():
    nombres = [types.FunctionDeclaration(**d).name for d in herramientas_ia.DECLARACIONES]
    assert nombres == ["buscar_cliente", "buscar_producto"]
    assert set(herramientas_ia.EJECUTORES) == set(nombres)


# ---------- Bucle (punto 10) ----------
def test_el_agente_consulta_herramientas_y_luego_responde(monkeypatch):
    p, fake = proveedor(monkeypatch, [
        pide(("buscar_cliente", {"nombre": "rosita"}), ("buscar_producto", {"texto": "aroz"})),
        texto(JSON_OK),
    ])
    trazas = []
    assert p.leer_hoja(b"x", "image/jpeg", trazas=trazas, presupuesto=presupuesto()) == JSON_OK
    assert len(fake.llamadas) == 2
    # La 2.ª llamada lleva la petición del modelo y las respuestas de las herramientas
    historial = fake.llamadas[1]["contents"]
    assert [c.role for c in historial] == ["user", "model", "user"]
    respuestas = [pt.function_response.name for pt in historial[2].parts]
    assert respuestas == ["buscar_cliente", "buscar_producto"]
    # Con herramientas no se fuerza el JSON; las herramientas viajan en la config
    assert fake.llamadas[0]["config"].tools and not fake.llamadas[0]["config"].response_mime_type
    # Trazas (punto 12)
    assert [(t["herramienta"], t["entrada"], t["estado"]) for t in trazas] == [
        ("buscar_cliente (agente)", "rosita", "encontrado"),
        ("buscar_producto (agente)", "aroz", "no_encontrado"),
    ]


def test_ultima_iteracion_va_sin_herramientas_y_con_json(monkeypatch):
    # El modelo pide herramientas SIEMPRE; con MAX_ITERACIONES=3 la 3.ª llamada es la forzada
    p, fake = proveedor(monkeypatch, [pide(("buscar_cliente", {"nombre": "x"})), pide(("buscar_cliente", {"nombre": "y"})), texto(JSON_OK)],
                        max_iteraciones=3)
    assert p.leer_hoja(b"x", "image/jpeg", presupuesto=presupuesto()) == JSON_OK
    assert len(fake.llamadas) == 3
    final = fake.llamadas[2]
    assert not final["config"].tools
    assert final["config"].response_mime_type == "application/json"
    # La llamada final recibe lo que respondieron las herramientas, en texto
    assert "buscar_cliente('x')" in final["contents"][1].parts[0].text


def test_nunca_se_pasa_de_max_iteraciones(monkeypatch):
    p, fake = proveedor(monkeypatch, [pide(("buscar_cliente", {"nombre": "x"}))], max_iteraciones=2)
    # La 2.ª (última) llamada devuelve otra petición de herramienta sin texto -> respuesta vacía
    with pytest.raises(FalloProveedor):
        p.leer_hoja(b"x", "image/jpeg", presupuesto=presupuesto())
    assert len(fake.llamadas) == 2


def test_max_iteraciones_1_es_una_sola_llamada_sin_herramientas(monkeypatch):
    p, fake = proveedor(monkeypatch, [texto(JSON_OK)], max_iteraciones=1)
    p.leer_hoja(b"x", "image/jpeg", presupuesto=presupuesto())
    assert len(fake.llamadas) == 1 and not fake.llamadas[0]["config"].tools
    assert fake.llamadas[0]["config"].response_mime_type == "application/json"


def test_json_con_comillas_de_codigo_se_acepta(monkeypatch):
    p, fake = proveedor(monkeypatch, [texto("```json\n" + JSON_OK + "\n```")])
    assert p.leer_hoja(b"x", "image/jpeg", presupuesto=presupuesto()) == JSON_OK
    assert len(fake.llamadas) == 1


def test_texto_que_no_es_json_fuerza_la_llamada_final(monkeypatch):
    p, fake = proveedor(monkeypatch, [texto("Claro, aquí tienes la lectura"), texto(JSON_OK)])
    assert p.leer_hoja(b"x", "image/jpeg", presupuesto=presupuesto()) == JSON_OK
    assert len(fake.llamadas) == 2 and fake.llamadas[1]["config"].response_mime_type == "application/json"


def test_herramienta_caida_no_tumba_la_lectura(monkeypatch):
    def rota(args):
        raise RuntimeError("BD caída")

    p, fake = proveedor(monkeypatch, [pide(("buscar_cliente", {"nombre": "x"})), texto(JSON_OK)],
                        herramientas={"buscar_cliente": rota})
    trazas = []
    assert p.leer_hoja(b"x", "image/jpeg", trazas=trazas, presupuesto=presupuesto()) == JSON_OK
    assert trazas[0]["estado"] == "error" and "BD caída" in trazas[0]["detalle"]


def test_herramienta_inventada_por_el_modelo(monkeypatch):
    p, _ = proveedor(monkeypatch, [pide(("borrar_todo", {"a": "b"})), texto(JSON_OK)])
    trazas = []
    p.leer_hoja(b"x", "image/jpeg", trazas=trazas, presupuesto=presupuesto())
    assert trazas[0]["estado"] == "error" and "desconocida" in trazas[0]["detalle"]


def test_suma_tokens_de_todas_las_vueltas(monkeypatch):
    p, _ = proveedor(monkeypatch, [pide(("buscar_cliente", {"nombre": "x"}), total=1500), texto(JSON_OK, total=2000)])
    pres = presupuesto()
    p.leer_hoja(b"x", "image/jpeg", presupuesto=pres)
    assert p.uso["llamadas"] == 2 and p.uso["total"] == 3500 and pres.tokens == 3500


# ---------- Tope de tokens acumulado (punto 3) ----------
def test_tope_de_tokens_corta_antes_de_otra_llamada(monkeypatch):
    p, fake = proveedor(monkeypatch, [pide(("buscar_cliente", {"nombre": "x"}), total=1200), texto(JSON_OK)])
    with pytest.raises(FalloProveedor) as exc:
        p.leer_hoja(b"x", "image/jpeg", presupuesto=presupuesto(tokens=1000))
    assert exc.value.codigo == "tokens"
    assert len(fake.llamadas) == 1      # no se gastó una 2.ª llamada


# ---------- Tiempo total (punto 2) ----------
def test_sin_tiempo_total_no_se_llama_a_gemini(monkeypatch):
    t = {"ahora": 0.0}
    pres = presupuesto(tiempo=10, reloj=lambda: t["ahora"])
    t["ahora"] = 11.0
    p, fake = proveedor(monkeypatch, [texto(JSON_OK)])
    with pytest.raises(FalloProveedor) as exc:
        p.leer_hoja(b"x", "image/jpeg", presupuesto=pres)
    assert exc.value.codigo == "timeout" and fake.llamadas == []


def test_el_timeout_de_cada_llamada_no_pasa_del_tiempo_que_queda(monkeypatch):
    t = {"ahora": 0.0}
    pres = presupuesto(tiempo=40, reloj=lambda: t["ahora"])
    p, fake = proveedor(monkeypatch, [texto("no es json"), texto(JSON_OK)])
    t["ahora"] = 25.0   # quedan 15 s: la llamada tendrá 15 s y no los 30 s normales
    p.leer_hoja(b"x", "image/jpeg", presupuesto=pres)
    assert fake.timeouts[0] == 15000


def test_saturado_sin_tiempo_para_reintentar_da_timeout(monkeypatch):
    t = {"ahora": 0.0}
    pres = presupuesto(tiempo=10, reloj=lambda: t["ahora"])
    p, fake = proveedor(monkeypatch, [Exception("503 UNAVAILABLE")])
    t["ahora"] = 9.0    # queda 1 s (< pausa de 2 s)
    with pytest.raises(FalloProveedor) as exc:
        p.leer_hoja(b"x", "image/jpeg", presupuesto=pres)
    assert exc.value.codigo == "timeout" and len(fake.llamadas) == 1
