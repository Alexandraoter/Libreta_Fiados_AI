"""Errores de la capa de IA. Son independientes de cualquier proveedor."""


class FalloProveedor(Exception):
    """Fallo al llamar a la IA.

    codigo:
      - 'timeout': la IA tardó más del límite (por llamada o en total: TIMEOUT_TOTAL_SEGUNDOS)
      - 'cuota':   se agotó el límite de uso (error 429)
      - 'tokens':  se superó MAX_TOKENS_ACUMULADOS sumando todos los reintentos
      - 'api':     cualquier otra caída o error de conexión
    """

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
