"""Implementación del proveedor con Google Gemini. Único archivo que importa `genai`.

`leer_hoja` es un pequeño agente (bucle de herramientas) con estos límites:
  - MAX_ITERACIONES: máximo de llamadas a Gemini por lectura.
  - Tiempo total y tokens acumulados: los lleva el `Presupuesto` que crea main.py.
  - La ÚLTIMA iteración siempre va SIN herramientas y con JSON obligatorio, para garantizar
    una respuesta final estructurada aunque el modelo siguiera pidiendo consultas.
Con MAX_ITERACIONES=1 no hay herramientas: es una sola llamada, como antes.
"""
import json
import os
import time

from google import genai
from google.genai import types

from . import herramientas_ia
from .errores import FalloProveedor
from .presupuesto import Presupuesto
from .prompts import construir_prompt

PAUSA_SATURADA_S = 2   # espera antes de reintentar cuando Gemini está saturado (error 503)


def _es_timeout(e: Exception) -> bool:
    nombre = type(e).__name__.lower()
    texto = str(e).lower()
    return (
        isinstance(e, TimeoutError)
        or "timeout" in nombre
        or "timed out" in texto
        or "deadline" in texto
    )


def _es_cuota(e: Exception) -> bool:
    texto = (type(e).__name__ + " " + str(e)).lower()
    return (
        "429" in texto
        or "resource_exhausted" in texto
        or "quota" in texto
        or "rate limit" in texto
    )


def _es_saturada(e: Exception) -> bool:
    """Gemini está sobrecargado (503). Suele durar segundos: vale la pena reintentar una vez."""
    texto = (type(e).__name__ + " " + str(e)).lower()
    return "503" in texto or "unavailable" in texto or "high demand" in texto


def _json_limpio(texto: str) -> str | None:
    """Devuelve el texto si es JSON válido (quitando ```json ... ``` si lo trae); si no, None."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    try:
        json.loads(t)
    except ValueError:
        return None
    return t


class GeminiProveedor:
    def __init__(
        self, api_key: str | None, modelo: str, timeout_s: int, max_tokens: int,
        max_iteraciones: int = 4, herramientas: dict | None = None,
    ):
        self.modelo = modelo
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.api_key = api_key
        self.max_iteraciones = max(1, max_iteraciones)
        # nombre de herramienta -> función que la ejecuta (se puede reemplazar en las pruebas)
        self.herramientas = herramientas if herramientas is not None else herramientas_ia.EJECUTORES
        self._tool = types.Tool(
            function_declarations=[types.FunctionDeclaration(**d) for d in herramientas_ia.DECLARACIONES]
        )
        # Tokens acumulados de todas las llamadas de este objeto (lo usa eval/ para el costo)
        self.uso = {"llamadas": 0, "entrada": 0, "salida": 0, "total": 0}

    # ---------- configuración de cada llamada ----------
    def _config(self, nivel: str, con_herramientas: bool) -> types.GenerateContentConfig:
        """Con herramientas: sin JSON forzado (Gemini no siempre admite ambos a la vez).
        Sin herramientas (llamada final): JSON obligatorio."""
        extra = {}
        if con_herramientas:
            extra["tools"] = [self._tool]
            extra["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        else:
            extra["response_mime_type"] = "application/json"
        return types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=self.max_tokens,
            # Opcional: MINIMAL, LOW, MEDIUM o HIGH. Vacío = el comportamiento por defecto del modelo.
            thinking_config=types.ThinkingConfig(thinking_level=nivel) if nivel else None,
            **extra,
        )

    # ---------- una llamada a Gemini ----------
    def _llamar(self, contenido: list, config, presupuesto: Presupuesto):
        """UNA llamada. Reintenta una vez si Gemini está saturado (503). Suma los tokens."""
        respuesta = None
        for intento in range(2):
            presupuesto.verificar()   # fuera del try: su error no debe confundirse con uno de Gemini
            try:
                client = genai.Client(
                    api_key=self.api_key,
                    # El timeout de la llamada nunca pasa del tiempo total que queda
                    http_options=types.HttpOptions(
                        timeout=int(presupuesto.timeout_llamada_s(self.timeout_s) * 1000)
                    ),
                )
                respuesta = client.models.generate_content(
                    model=self.modelo, contents=contenido, config=config,
                )
                break
            except Exception as e:
                print("Fallo de Gemini:", type(e).__name__, e)
                if _es_timeout(e):
                    raise FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo.")
                if _es_cuota(e):
                    raise FalloProveedor(
                        "cuota",
                        "Se agotó el límite de uso de la IA. Espera un minuto e intenta de nuevo.",
                    )
                if _es_saturada(e):
                    if intento == 0:
                        restante = presupuesto.restante_s()
                        if restante is not None and restante <= PAUSA_SATURADA_S:
                            # No alcanza el tiempo total para esperar y reintentar
                            raise FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo.")
                        time.sleep(PAUSA_SATURADA_S)
                        continue
                    raise FalloProveedor(
                        "api", "La IA está saturada en este momento. Intenta de nuevo en unos segundos."
                    )
                raise FalloProveedor(
                    "api", "No se pudo conectar con la IA. Revisa la clave y vuelve a intentar."
                )

        u = respuesta.usage_metadata
        self.uso["llamadas"] += 1
        if u:
            entrada = u.prompt_token_count or 0
            salida = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
            total = u.total_token_count or (entrada + salida)
            self.uso["entrada"] += entrada
            self.uso["salida"] += salida
            self.uso["total"] += total
            presupuesto.registrar(total)   # el tope de tokens suma TODAS las llamadas de la lectura
        return respuesta

    # ---------- una herramienta pedida por el modelo ----------
    def _ejecutar(self, llamada, trazas: list, resumen: list) -> dict:
        """Ejecuta la herramienta, deja una traza y devuelve lo que se le responde al modelo."""
        nombre = llamada.name or ""
        args = dict(llamada.args or {})
        entrada = next((str(v) for v in args.values()), "")
        t0 = time.perf_counter()
        try:
            if nombre not in self.herramientas:
                raise KeyError(f"herramienta desconocida: {nombre}")
            resultado = self.herramientas[nombre](args)
            estado = resultado.get("estado", "ok")
            nombres = [c["nombre"] for c in resultado.get("candidatos", [])]
            detalle = "candidatos: " + (", ".join(nombres) if nombres else "ninguno")
        except Exception as e:
            # Una herramienta caída (p. ej. la BD) no tumba la lectura: el modelo sigue sin ella
            print("Fallo de una herramienta del agente:", nombre, type(e).__name__, e)
            resultado = {"error": "La herramienta no está disponible. Continúa sin ella."}
            estado, detalle = "error", f"{type(e).__name__}: {e}"
        trazas.append({
            "herramienta": f"{nombre} (agente)",
            "entrada": entrada,
            "estado": estado,
            "detalle": detalle,
            "ms": round((time.perf_counter() - t0) * 1000),
        })
        resumen.append(f"- {nombre}({entrada!r}): {estado}; {detalle}")
        return resultado

    # ---------- el bucle del agente ----------
    def leer_hoja(
        self, img: bytes, mime: str, correccion: str | None = None,
        trazas: list | None = None, presupuesto: Presupuesto | None = None,
    ) -> str:
        trazas = trazas if trazas is not None else []
        presupuesto = presupuesto or Presupuesto.desde_entorno()
        nivel = os.getenv("THINKING_LEVEL", "").strip().upper()
        con_herramientas = self.max_iteraciones > 1

        pregunta = types.Content(role="user", parts=[
            types.Part.from_bytes(data=img, mime_type=mime),
            types.Part.from_text(text=construir_prompt(correccion, con_herramientas)),
        ])
        historial = [pregunta]   # conserva las respuestas del modelo tal cual (con sus firmas de razonamiento)
        resumen: list[str] = []  # lo que devolvieron las herramientas, en texto, para la llamada final
        forzar_final = not con_herramientas
        iteracion = 0

        while True:
            iteracion += 1
            if forzar_final or iteracion >= self.max_iteraciones:
                # Última iteración: SIN herramientas y con JSON obligatorio.
                contenido = [pregunta]
                if resumen:
                    contenido.append(types.Content(role="user", parts=[types.Part.from_text(text=(
                        "Resultados de tus consultas a la base de datos (solo lectura):\n"
                        + "\n".join(resumen)
                        + "\nYa no puedes usar herramientas. Úsalos solo para confirmar tu lectura de la "
                        "foto y responde AHORA solo con el JSON final."
                    ))]))
                respuesta = self._llamar(contenido, self._config(nivel, False), presupuesto)
                texto = (respuesta.text or "").strip()
                if not texto:
                    raise FalloProveedor("api", "La IA no devolvió respuesta. Intenta de nuevo.")
                return texto

            respuesta = self._llamar(historial, self._config(nivel, True), presupuesto)
            pedidas = getattr(respuesta, "function_calls", None) or []
            if not pedidas:
                # El modelo ya respondió. Si es JSON válido, listo; si no, se pide la salida final forzada.
                texto = _json_limpio((respuesta.text or "").strip())
                if texto is not None:
                    return texto
                forzar_final = True
                continue

            historial.append(respuesta.candidates[0].content)
            historial.append(types.Content(role="user", parts=[
                types.Part.from_function_response(name=p.name, response=self._ejecutar(p, trazas, resumen))
                for p in pedidas
            ]))
