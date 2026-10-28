"""Límites compartidos de UNA lectura de hoja: tiempo total y tokens acumulados.

main.py crea un `Presupuesto` por foto y se lo pasa al proveedor. Así el tope cubre
TODOS los reintentos (validación fallida, 503) y todas las vueltas del agente, no solo
una llamada suelta.

  - TIMEOUT_TOTAL_SEGUNDOS: tiempo máximo de toda la lectura (por defecto 60). 0 = sin tope.
  - MAX_TOKENS_ACUMULADOS:  tokens máximos sumados entre llamadas (por defecto 50000). 0 = sin tope.

El tope de tokens se comprueba ANTES de cada llamada nueva: una llamada en curso nunca se
corta a la mitad (esa la acota MAX_TOKENS), pero no se empieza otra si ya se superó el tope.
"""
import os
import time

from .errores import FalloProveedor


class Presupuesto:
    def __init__(self, timeout_total_s: float | None, max_tokens: int | None, reloj=time.monotonic):
        self._reloj = reloj                      # inyectable para probar el tiempo sin esperar
        self._fin = reloj() + timeout_total_s if timeout_total_s and timeout_total_s > 0 else None
        self.max_tokens = max_tokens if max_tokens and max_tokens > 0 else None
        self.tokens = 0                          # suma de los tokens de todas las llamadas

    @classmethod
    def desde_entorno(cls) -> "Presupuesto":
        """Lee los topes de .env. Lanza ValueError si alguno no es un número."""
        return cls(
            float(os.getenv("TIMEOUT_TOTAL_SEGUNDOS", "60")),
            int(os.getenv("MAX_TOKENS_ACUMULADOS", "50000")),
        )

    def restante_s(self) -> float | None:
        """Segundos que quedan, o None si no hay tope de tiempo."""
        return None if self._fin is None else self._fin - self._reloj()

    def timeout_llamada_s(self, por_llamada_s: float) -> float:
        """Timeout de UNA llamada: el normal, pero sin pasarse del tiempo total que queda."""
        restante = self.restante_s()
        return por_llamada_s if restante is None else max(1.0, min(por_llamada_s, restante))

    def registrar(self, tokens: int) -> None:
        self.tokens += tokens

    def verificar(self) -> None:
        """Lanza FalloProveedor si ya no hay tiempo o se superó el tope de tokens."""
        restante = self.restante_s()
        if restante is not None and restante <= 0:
            raise FalloProveedor("timeout", "La IA tardó demasiado. Intenta de nuevo.")
        if self.max_tokens is not None and self.tokens > self.max_tokens:
            raise FalloProveedor(
                "tokens",
                "Esta hoja consumió más IA de la permitida. Prueba con una foto más clara o con menos líneas.",
            )
