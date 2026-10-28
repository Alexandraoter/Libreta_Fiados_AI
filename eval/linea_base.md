## 4. Línea base de evaluación

Medida el 2026-10-27 con el modelo `gemini-3.6-flash`: 10 caso(s) dorado(s) × 1 pasada(s) = 10 ejecuciones. Cada ejecución corre el flujo real (lectura con la IA + búsqueda de clientes y productos en la BD).

| Cifra | Valor |
|---|---|
| Exactitud de movimientos | 100.0 % |
| Latencia mediana | 20.1 s |
| Costo mediano por hoja | sin medir (define PRECIO_ENTRADA_USD_M y PRECIO_SALIDA_USD_M en .env) |
| Tasa de fallos | 10.0 % |

Cómo se calcula cada cifra:
- **Exactitud:** un movimiento es correcto si coinciden el tipo, el cliente (como lo ve el tendero) y el monto. Inventar movimientos de más también resta. Se calcula solo sobre las ejecuciones 
que terminaron sin error; los fallos van aparte, en la tasa de fallos.
- **Latencia:** segundos desde que llega la foto hasta tener los movimientos con clientes y productos resueltos, incluidos los reintentos. Mediana de las ejecuciones exitosas.
- **Costo:** tokens de entrada y salida por el precio por millón de tokens definido en `.env`. Mediana de las ejecuciones exitosas.
- **Tasa de fallos:** ejecuciones que terminaron en error (timeout, cuota, caída de la API o JSON inválido después de los reintentos).

Ejecuciones que necesitaron más de un intento: 0.0 %.
