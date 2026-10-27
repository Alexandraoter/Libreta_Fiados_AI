"""Evaluación con casos dorados: mide la línea base del sistema.

Cada caso es una foto real con la respuesta correcta escrita a mano por el equipo
(eval/casos/casos.json). El script corre el flujo real de la app (lectura con la IA +
búsqueda de clientes y productos en la BD), compara con lo esperado y calcula 4 cifras:
exactitud, latencia mediana, costo mediano y tasa de fallos.

Uso, desde la raíz del repo y con la BD levantada (docker compose up -d db):
    python -m eval.run                     # una pasada por caso
    python -m eval.run --repeticiones 3    # 3 pasadas: la mediana sale más estable
    python -m eval.run --pausa 5           # segundos entre llamadas (evita el error 429)
    python -m eval.run --validar           # solo revisa casos.json, no llama a la IA
"""
import argparse
import json
import os
import statistics
import time
import unicodedata
from datetime import date
from pathlib import Path

AQUI = Path(__file__).parent
CASOS = AQUI / "casos" / "casos.json"
RESULTADOS = AQUI / "resultados.json"
LINEA_BASE = AQUI / "linea_base.md"
TIPOS = {"venta", "fiado", "abono"}
MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


# ---------- Comparación con lo esperado ----------
def normalizar(texto):
    """Minúsculas, sin tildes y sin espacios de más: 'Doña  ROSA' -> 'dona rosa'."""
    if texto is None:
        return None
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    )
    return " ".join(sin_tildes.lower().split())


def mismo_cliente(esperado, obtenido) -> bool:
    """`esperado` puede ser None (sin cliente) o una lista de formas aceptadas."""
    if esperado is None:
        return not obtenido
    aceptados = esperado if isinstance(esperado, list) else [esperado]
    return normalizar(obtenido) in {normalizar(a) for a in aceptados}


def mismo_monto(esperado, obtenido) -> bool:
    """null solo coincide con null: un monto inventado cuenta como error."""
    if esperado is None or obtenido is None:
        return esperado is None and obtenido is None
    return abs(float(esperado) - float(obtenido)) < 0.5


def movimiento_correcto(esperado: dict, obtenido: dict) -> bool:
    return (
        esperado["tipo"] == obtenido.get("tipo")
        and mismo_cliente(esperado.get("cliente"), obtenido.get("cliente"))
        and mismo_monto(esperado.get("monto"), obtenido.get("monto"))
    )


def puntuar(esperados: list, obtenidos: list) -> tuple[int, int]:
    """Devuelve (aciertos, total). Cada movimiento esperado se empareja con uno distinto
    de los obtenidos. El total es el mayor de los dos largos: inventar movimientos
    de más también resta puntos."""
    libres = list(obtenidos)
    aciertos = 0
    for esperado in esperados:
        for obtenido in libres:
            if movimiento_correcto(esperado, obtenido):
                libres.remove(obtenido)
                aciertos += 1
                break
    return aciertos, max(len(esperados), len(obtenidos))


# ---------- Casos ----------
def cargar_casos() -> list:
    return json.loads(CASOS.read_text(encoding="utf-8"))


def validar_casos(casos: list) -> list[str]:
    """Revisa casos.json y devuelve la lista de problemas (vacía si todo está bien)."""
    if not casos:
        return ["casos.json está vacío"]
    errores, ids = [], set()
    for i, caso in enumerate(casos, 1):
        nombre = caso.get("id") or f"#{i}"
        if not caso.get("id"):
            errores.append(f"Caso #{i}: falta 'id'")
        elif caso["id"] in ids:
            errores.append(f"{nombre}: el id está repetido")
        ids.add(caso.get("id"))

        foto = AQUI / "casos" / caso.get("foto", "")
        if not caso.get("foto") or not foto.is_file():
            errores.append(f"{nombre}: no existe la foto {caso.get('foto')!r} en eval/casos/")
        elif foto.suffix.lower() not in MIMES:
            errores.append(f"{nombre}: la foto debe ser .jpg o .png")

        esperado = caso.get("esperado")
        if not isinstance(esperado, list):
            errores.append(f"{nombre}: 'esperado' debe ser una lista (puede ser [])")
            continue
        for m in esperado:
            if m.get("tipo") not in TIPOS:
                errores.append(f"{nombre}: tipo inválido {m.get('tipo')!r}")
            if "cliente" not in m or "monto" not in m:
                errores.append(f"{nombre}: cada movimiento necesita 'cliente' y 'monto' (pueden ser null)")
    return errores


# ---------- Ejecución ----------
def cliente_visible(mov: dict):
    """El cliente tal como lo ve el tendero: el nombre de la BD si se identificó, o el texto leído."""
    r = mov.get("cliente_resuelto") or {}
    if r.get("estado") == "encontrado":
        return r["elegido"]["nombre"]
    return mov.get("cliente")


def ejecutar_real(img: bytes, mime: str):
    """Corre el flujo real de la app. Devuelve (movimientos, intentos, uso_de_tokens)."""
    from fastapi import HTTPException

    from app.ia import obtener_proveedor
    from app.web.main import leer_hoja, resolver_en_bd

    proveedor = obtener_proveedor()
    try:
        hoja, intentos = leer_hoja(img, mime, proveedor)
    except HTTPException as e:
        # "No encontré movimientos" es la respuesta correcta para una hoja vacía.
        if e.status_code == 422 and "No encontré movimientos" in str(e.detail):
            return [], 1, getattr(proveedor, "uso", {})
        raise
    datos = resolver_en_bd(hoja)
    movimientos = [
        {"tipo": m.get("tipo"), "cliente": cliente_visible(m), "monto": m.get("monto")}
        for m in datos["movimientos"]
    ]
    return movimientos, intentos, getattr(proveedor, "uso", {})


def _precio(nombre: str):
    valor = os.getenv(nombre, "").strip()
    return float(valor) if valor else None


def costo_usd(entrada: int, salida: int):
    """Tokens x precio por millón. None si no se definieron los precios en .env."""
    precio_entrada = _precio("PRECIO_ENTRADA_USD_M")
    precio_salida = _precio("PRECIO_SALIDA_USD_M")
    if precio_entrada is None or precio_salida is None:
        return None
    return (entrada * precio_entrada + salida * precio_salida) / 1_000_000


def correr(casos: list, repeticiones: int, pausa: float, ejecutar=ejecutar_real) -> list[dict]:
    corridas = []
    total = len(casos) * repeticiones
    n = 0
    for caso in casos:
        foto = AQUI / "casos" / caso["foto"]
        img, mime = foto.read_bytes(), MIMES[foto.suffix.lower()]
        for rep in range(1, repeticiones + 1):
            n += 1
            fila = {"caso": caso["id"], "rep": rep}
            t0 = time.perf_counter()
            try:
                obtenidos, intentos, uso = ejecutar(img, mime)
                fila["ms"] = round((time.perf_counter() - t0) * 1000)
                aciertos, tot = puntuar(caso["esperado"], obtenidos)
                entrada, salida = uso.get("entrada", 0), uso.get("salida", 0)
                fila.update(
                    ok=True, error=None, intentos=intentos, aciertos=aciertos, total=tot,
                    tokens_total=uso.get("total", 0), costo_usd=costo_usd(entrada, salida),
                    obtenido=obtenidos,
                )
                print(f"[{n}/{total}] {caso['id']} (pasada {rep}): {aciertos}/{tot} correctos"
                      f" · {fila['ms'] / 1000:.1f} s · {fila['tokens_total']} tokens")
            except Exception as e:
                fila["ms"] = round((time.perf_counter() - t0) * 1000)
                detalle = getattr(e, "detail", None) or str(e)
                fila.update(
                    ok=False, error=f"{type(e).__name__}: {detalle}", intentos=0, aciertos=0,
                    total=len(caso["esperado"]), tokens_total=0, costo_usd=None, obtenido=[],
                )
                print(f"[{n}/{total}] {caso['id']} (pasada {rep}): FALLÓ -> {fila['error']}")
            corridas.append(fila)
            if n < total and pausa > 0:
                time.sleep(pausa)
    return corridas


# ---------- Cifras ----------
def mediana(valores: list):
    return statistics.median(valores) if valores else None


def resumir(corridas: list[dict]) -> dict:
    ok = [c for c in corridas if c["ok"]]
    aciertos = sum(c["aciertos"] for c in ok)
    total = sum(c["total"] for c in ok)
    return {
        "ejecuciones": len(corridas),
        "exactitud": aciertos / total if total else None,
        "latencia_mediana_s": mediana([c["ms"] / 1000 for c in ok]),
        "costo_mediano_usd": mediana([c["costo_usd"] for c in ok if c["costo_usd"] is not None]),
        "tokens_medianos": mediana([c["tokens_total"] for c in ok]),
        "tasa_fallos": (len(corridas) - len(ok)) / len(corridas) if corridas else None,
        "con_reintento": sum(1 for c in ok if c["intentos"] > 1) / len(ok) if ok else None,
    }


def _pct(x):
    return "sin datos" if x is None else f"{x * 100:.1f} %"


def _seg(x):
    return "sin datos" if x is None else f"{x:.1f} s"


def _costo(x, tokens):
    if x is None:
        return "sin medir (define PRECIO_ENTRADA_USD_M y PRECIO_SALIDA_USD_M en .env)"
    return f"US$ {x:.5f} por hoja (≈ {tokens:,.0f} tokens)"


def bloque_decisiones(resumen: dict, modelo: str, n_casos: int, repeticiones: int) -> str:
    """Texto listo para pegar en docs/decisiones.md."""
    return f"""## 4. Línea base de evaluación

Medida el {date.today().isoformat()} con el modelo `{modelo}`: {n_casos} caso(s) dorado(s) \
× {repeticiones} pasada(s) = {resumen['ejecuciones']} ejecuciones. Cada ejecución corre el \
flujo real (lectura con la IA + búsqueda de clientes y productos en la BD).

| Cifra | Valor |
|---|---|
| Exactitud de movimientos | {_pct(resumen['exactitud'])} |
| Latencia mediana | {_seg(resumen['latencia_mediana_s'])} |
| Costo mediano por hoja | {_costo(resumen['costo_mediano_usd'], resumen['tokens_medianos'] or 0)} |
| Tasa de fallos | {_pct(resumen['tasa_fallos'])} |

Cómo se calcula cada cifra:
- **Exactitud:** un movimiento es correcto si coinciden el tipo, el cliente (como lo ve el \
tendero) y el monto. Inventar movimientos de más también resta. Se calcula solo sobre las ejecuciones 
que terminaron sin error; los fallos van aparte, en la tasa de fallos.
- **Latencia:** segundos desde que llega la foto hasta tener los movimientos con clientes y \
productos resueltos, incluidos los reintentos. Mediana de las ejecuciones exitosas.
- **Costo:** tokens de entrada y salida por el precio por millón de tokens definido en `.env`. \
Mediana de las ejecuciones exitosas.
- **Tasa de fallos:** ejecuciones que terminaron en error (timeout, cuota, caída de la API o \
JSON inválido después de los reintentos).

Ejecuciones que necesitaron más de un intento: {_pct(resumen['con_reintento'])}.
"""


def main():
    from dotenv import load_dotenv

    load_dotenv()
    ap = argparse.ArgumentParser(description="Evaluación con casos dorados")
    ap.add_argument("--repeticiones", type=int, default=1, help="pasadas por caso (por defecto 1)")
    ap.add_argument("--pausa", type=float, default=3.0, help="segundos entre llamadas (por defecto 3)")
    ap.add_argument("--validar", action="store_true", help="solo revisa casos.json")
    args = ap.parse_args()

    if not CASOS.is_file():
        raise SystemExit(f"No existe {CASOS}")
    casos = cargar_casos()
    errores = validar_casos(casos)
    if errores:
        print("casos.json tiene problemas:")
        for e in errores:
            print(" -", e)
        raise SystemExit(1)
    print(f"{len(casos)} caso(s) válido(s).")
    if args.validar:
        return

    simulada = os.getenv("PROVEEDOR_IA", "gemini").lower() == "falso"
    if simulada:
        print("AVISO: PROVEEDOR_IA=falso. La IA es simulada: estas cifras NO sirven como línea base.")
    modelo = "IA simulada" if simulada else os.getenv("MODEL_NAME", "gemini-3.6-flash")

    corridas = correr(casos, max(1, args.repeticiones), args.pausa)
    resumen = resumir(corridas)
    bloque = bloque_decisiones(resumen, modelo, len(casos), max(1, args.repeticiones))

    RESULTADOS.write_text(
        json.dumps(
            {"fecha": date.today().isoformat(), "modelo": modelo, "resumen": resumen, "corridas": corridas},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    if not simulada:
        LINEA_BASE.write_text(bloque, encoding="utf-8")
    print("\n" + bloque)
    if resumen["tokens_medianos"] == 0:
        print("AVISO: Gemini no reportó tokens. Revisa que gemini.py sume `uso` (ver pasos).")
    print(f"Detalle de cada ejecución: {RESULTADOS}")


if __name__ == "__main__":
    main()
