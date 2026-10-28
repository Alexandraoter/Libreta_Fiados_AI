"""Pruebas de la evaluación (no llaman a Gemini ni a la base de datos)."""
from eval.run import (
    cargar_casos, correr, mediana, mismo_cliente, mismo_monto, normalizar,
    puntuar, resumir, validar_casos,
)

FIAD = {"tipo": "fiado", "cliente": ["Rosa Martínez"], "monto": 8400}
OBT = {"tipo": "fiado", "cliente": "Rosa Martínez", "monto": 8400}


def test_normalizar_quita_tildes_y_mayusculas():
    assert normalizar("  Doña  ROSA ") == "dona rosa"


def test_cliente_acepta_varias_formas():
    assert mismo_cliente(["Rosa Martínez", "Rosita"], "rosita")
    assert not mismo_cliente(["Rosa Martínez"], "Pedro Gómez")
    assert mismo_cliente(None, None)


def test_monto_null_solo_coincide_con_null():
    assert mismo_monto(None, None)
    assert not mismo_monto(None, 4000)
    assert not mismo_monto(9000, None)
    assert mismo_monto(8400, 8400.0)


def test_puntuar_todo_correcto():
    assert puntuar([FIAD], [OBT]) == (1, 1)


def test_inventar_movimientos_resta():
    extra = {"tipo": "abono", "cliente": "Luz", "monto": 100}
    assert puntuar([FIAD], [OBT, extra]) == (1, 2)


def test_no_se_empareja_dos_veces_el_mismo_movimiento():
    assert puntuar([FIAD, FIAD], [OBT]) == (1, 2)


def test_resumir_mediana_y_tasa_de_fallos():
    corridas = [
        {"ok": True, "ms": 1000, "costo_usd": 0.001, "tokens_total": 100, "intentos": 1, "aciertos": 4, "total": 4},
        {"ok": True, "ms": 3000, "costo_usd": 0.003, "tokens_total": 300, "intentos": 2, "aciertos": 2, "total": 4},
        {"ok": False, "ms": 500, "costo_usd": None, "tokens_total": 0, "intentos": 0, "aciertos": 0, "total": 4},
    ]
    r = resumir(corridas)
    assert r["latencia_mediana_s"] == 2.0
    assert r["costo_mediano_usd"] == 0.002
    assert abs(r["tasa_fallos"] - 1 / 3) < 1e-9
    assert abs(r["exactitud"] - 6 / 8) < 1e-9
    assert r["con_reintento"] == 0.5
    assert mediana([]) is None


def test_casos_json_es_valido():
    assert validar_casos(cargar_casos()) == []


def test_correr_con_ia_simulada():
    caso = cargar_casos()[0]

    def perfecta(img, mime):
        obtenidos = [
            {"tipo": m["tipo"],
             "cliente": m["cliente"][0] if isinstance(m["cliente"], list) else m["cliente"],
             "monto": m["monto"]}
            for m in caso["esperado"]
        ]
        return obtenidos, 1, {"entrada": 1000, "salida": 200, "total": 1200}

    def rota(img, mime):
        raise TimeoutError("simulado")

    ok = correr([caso], 1, 0, ejecutar=perfecta)[0]
    assert ok["ok"] and ok["aciertos"] == ok["total"] == len(caso["esperado"])
    mal = correr([caso], 1, 0, ejecutar=rota)[0]
    assert not mal["ok"] and mal["aciertos"] == 0 and "TimeoutError" in mal["error"]
