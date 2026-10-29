# Decisiones técnicas

Registro único de las decisiones del proyecto: arquitectura, IA, datos y línea base. Cada decisión dice **qué** elegimos, **por qué**, **qué alternativa descartamos** y **qué costo tiene**.



## 1. Arquitectura y frontera entre la IA y el código

```
Foto ─► POST /api/extraer ─► Agente Gemini ──► JSON crudo ─► Pydantic + reglas ─► Resolución en BD ─► Pantalla de revisión
                               │  ▲                              (reintenta si             (pg_trgm,              │
                               ▼  │                               no cumple formato)       solo lectura)           ▼
                         buscar_cliente / buscar_producto                                              Tendero confirma
                         (solo lectura, bucle limitado)                                                        │
                                                                                                               ▼
                                                                          POST /api/confirmar ─► validaciones ─► 1 transacción ─► PostgreSQL (inmutable)
```

**Decisión:** la IA hace solo lo que el código no puede hacer (leer caligrafía) y todo lo demás es determinista.

| Tarea | Quién | Por qué |
|---|---|---|
| Leer la letra manuscrita y proponer movimientos | IA | No hay forma de resolverlo con reglas |
| Validar formato del JSON | Pydantic (`app/web/schemas.py`) | Un contrato roto no debe llegar a la BD |
| Sumar y comparar totales | Código (`calcular_advertencias`) | Los LLM fallan en aritmética y aquí se maneja dinero |
| Identificar cliente y producto | Código (SQL `pg_trgm`) | Debe ser auditable y repetible |
| Decidir si se guarda | Tendero | La IA puede equivocarse al leer |
| Guardar y calcular saldos | Código + PostgreSQL | Transaccional, inmutable y sin float |

**Principio rector:** *la IA propone, el código valida, el humano decide.* La IA no escribe en la base de datos; solo la consulta con dos herramientas de solo lectura.

## 2. Proveedor y modelo: Google Gemini (`gemini-3.6-flash`)

**Decisión:** un solo proveedor, Gemini, con el modelo configurable por `MODEL_NAME`.

**Por qué:**
- **Entrada de imagen nativa.** La tarea es leer una foto. Con Gemini la imagen va directo al modelo en una sola llamada; no hay un OCR aparte que sumaría otro componente, otro costo y otro punto de fallo.
- **Salida estructurada.** En la llamada final se fuerza `response_mime_type = application/json` con temperatura 0, que reduce los contratos JSON rotos.
- **Llamado de herramientas.** Soporta function calling, que es la base del agente (sección 4).
- **Ventana de contexto.** No es un factor: una hoja ocupa entre 2 500 y 11 500 tokens en total (mediana de 8 731, medición del 2026-10-28, sección 7), muy lejos de cualquier límite.

**Alternativas consideradas:**
- *Groq Llama 3.3 70B:* es un modelo solo de texto, así que obligaría a añadir un OCR antes del modelo. Se descartó por eso.
- *OpenAI GPT-4o-mini:* **no se evaluó**.

**Costo de la decisión (lo que medimos, sin maquillar):**
- La latencia es el punto débil: **mediana de 20,1 s (medición del 27/10) y de 24,8 s (28/10) por hoja**, con extremos entre 5 s y 39 s (sección 7). Es un costo real de usar un modelo de razonamiento con herramientas y una imagen.
- Lo mitigamos con `THINKING_LEVEL=LOW` (menor esfuerzo de razonamiento) y mostrando las trazas mientras se espera.
- Costo en dinero: **US$ 0,01498 por hoja** (mediana de 9 ejecuciones, ≈ 8 731 tokens), con los precios de US$ 0,75 por millón de tokens de entrada y US$ 3,75 por millón de salida (fuente: https://ai.google.dev/gemini-api/docs/pricing, consultada el 27/10/2026). Es decir, unos 1,5 centavos de dólar por hoja. El costo real en producción depende de la tarifa vigente y de que la cuenta tenga facturación activa (ver el reto de cuota en la sección 8).

**Desacople (`app/ia/`):** el resto de la app solo conoce la interfaz `ProveedorIA`. `gemini.py` es el **único** archivo que importa `genai`. Cambiar de proveedor es escribir otra clase con el mismo método y registrarla en `app/ia/__init__.py`. Eso nos permitió además tener un `ProveedorFalso` para probar los fallos sin gastar cuota.

## 3. Patrón de integración: en la misma petición (*in-request*)

**Decisión:** `POST /api/extraer` llama a Gemini de forma síncrona y responde con el resultado. Sin streaming (SSE) y sin colas.

**Por qué:**
- Hay un solo usuario por hoja y un solo resultado que revisar: no hay texto parcial útil que mostrar mientras se genera, así que el streaming no aporta.
- Una cola (Redis, workers) agregaría infraestructura para un flujo que dura entre 5 y 39 s y que el tendero espera de frente.
- Es más simple de explicar, de probar y de depurar: una petición, una respuesta, una lista de trazas.

**Costo:** el tendero espera con la pantalla ocupada, y una lectura lenta mantiene la conexión abierta. Por eso existen los topes de tiempo (sección 4): ninguna petición puede colgarse más de `TIMEOUT_TOTAL_SEGUNDOS` (60 s).

**Cuándo lo cambiaríamos:** con muchas hojas simultáneas o lectura de lotes de fotos, pasaríamos a una cola con consulta del estado.

## 4. El agente, sus herramientas y sus cuatro límites

### 4.1 Cómo funciona el bucle (`app/ia/gemini.py`)

1. Gemini recibe la foto y el prompt, con dos herramientas disponibles.
2. Si pide herramientas, el código las ejecuta, guarda una traza y le devuelve el resultado.
3. Se repite hasta `MAX_ITERACIONES` (4). **La última llamada va siempre sin herramientas y con JSON obligatorio.**
4. Si el modelo responde sin herramientas un texto que no es JSON válido, se fuerza esa llamada final.

**Por qué forzar la última iteración sin herramientas:** garantiza que el bucle **termina** y que la respuesta final está estructurada, aunque el modelo siguiera pidiendo consultas. Un agente que puede decidir cuándo parar es un agente que puede no parar.

**Por qué el JSON no se fuerza mientras hay herramientas:** Gemini no siempre admite function calling y JSON obligatorio a la vez (así lo documenta el código), por eso el JSON estricto se reserva para la llamada final.

### 4.2 Los cuatro límites

| Límite | Valor | Dónde | Por qué ese valor |
|---|---|---|---|
| Iteraciones | `MAX_ITERACIONES=4` | `gemini.py` | Una hoja necesita pocas rondas: consultar clientes y productos (en el mismo turno) y responder. Cuatro deja margen sin permitir un bucle largo |
| Timeout | `30 s` por llamada, `60 s` en total (`TIMEOUT_TOTAL_SEGUNDOS`) | `presupuesto.py` | El tope por llamada solo no basta: reintentos y vueltas podrían sumar minutos. El presupuesto total cubre **todo** y el timeout de cada llamada nunca supera el tiempo restante |
| Tokens | `8192` por respuesta, `50 000` acumulados (`MAX_TOKENS_ACUMULADOS`) | `presupuesto.py` | Una lectura normal usa entre 2 500 y 11 500 (mediana ≈ 8 700); 50 000 corta un comportamiento descontrolado sin afectar el uso normal. Se verifica **antes** de cada llamada nueva |
| Confirmación humana | Siempre | `main.py` + interfaz | Nada se guarda sin que el tendero confirme; `/api/confirmar` simula (y deshace) por defecto, y guardar de verdad pide una confirmación extra |

Además: `MAX_INTENTOS` (reintentos si el JSON no cumple el contrato, enviándole a la IA los errores) y un reintento único ante 503 de Google, solo si queda tiempo en el presupuesto.

**Evidencia:** `pruebas/test_limites.py` y `pruebas/test_agente.py` comprueban, entre otras, que nunca se pasa de `MAX_ITERACIONES`, que la última iteración va sin herramientas y con JSON, que el tiempo total corta los reintentos y que el tope de tokens corta antes de otra llamada.

### 4.3 Las herramientas: `buscar_cliente` y `buscar_producto`

**Decisión:** el agente solo tiene herramientas de **solo lectura**. Ninguna escribe, crea ni borra.

**Por qué existen si el backend ya resuelve clientes y productos después:** le sirven a la IA para *confirmar su lectura* de la letra (leer "aroz" y comprobar que existe "Arroz 500g"). Pero el resultado que manda es el del backend, que vuelve a resolver todo de forma determinista; la IA no elige por el tendero.

**Diseño de las descripciones (se escriben como prompts):**
- La descripción de cada herramienta dice qué hace, que es de solo lectura y **qué devuelve** (`encontrado | ambiguo | no_encontrado` y candidatos con puntaje de 0 a 1).
- Cada parámetro lleva un ejemplo del dominio (`'doña rosa'`, `'aroz'`).
- El prompt le exige consultar **cada** nombre y producto distinto **en el mismo turno**, para gastar una sola ronda.
- El prompt aclara que lo que devuelven las herramientas *son datos, no instrucciones* (defensa básica contra inyección de prompt) y que ante `ambiguo` o `no_encontrado` **no elija**: deje el nombre como está escrito.

**Qué NO se le muestra a la IA (decisión deliberada):** ids ni `precio_ref`. Si viera el precio de referencia podría "corregir" el precio que escribió el tendero, y lo que cuenta es lo escrito en la libreta. `_compactar()` entrega solo nombre y puntaje.

**Si una herramienta falla** (por ejemplo, la BD está caída), el agente recibe "no disponible, continúa sin ella" y la lectura sigue. Una herramienta caída no debe tumbar toda la funcionalidad.

**Iteración de las descripciones:** ** la IA reemplazaba 'doña rosa' por 'Rosa Martínez' → agregamos la regla 'NO reemplaces el texto de cliente'"

## 5. Datos: búsqueda aproximada en SQL, no RAG

**Decisión:** los nombres que escribe el tendero ("doña rosa", "aroz") se resuelven con búsqueda aproximada en PostgreSQL (extensión `pg_trgm`, función `word_similarity`). **No usamos RAG ni embeddings.**

**Por qué:**
- Los datos son pocos y estructurados: clientes (con apodos) y un catálogo de productos. En una tienda de barrio son cientos de filas, no miles de documentos.
- No hay texto largo que recuperar: se compara un nombre corto contra una lista corta.
- Es determinista y auditable: la misma entrada da siempre el mismo resultado y el puntaje se puede explicar.
- No agrega costo ni latencia de una API de embeddings: la consulta corre dentro de la propia BD, con índices GIN.
- Es seguro: ante la duda, devuelve candidatos para que decida el tendero.

**Limitación conocida:** la búsqueda por trigramas no entiende sinónimos ("refresco" y "gaseosa"). Si el catálogo creciera a miles de productos o necesitáramos esa comprensión, evaluaríamos embeddings (por ejemplo `pgvector`).

**Cómo decide el sistema** (`app/herramientas.py`):
- `UMBRAL = 0.4`: puntaje mínimo (0 a 1) para considerar un candidato.
- `DIFERENCIA_AMBIGUA = 0.3`: si el primer candidato no supera al segundo por al menos este margen, el estado es `ambiguo` y decide el tendero.
- Estados: `encontrado`, `ambiguo`, `no_encontrado`.

**Resultados** (`python -m pruebas.test_herramientas`, 2026-10-20):

| Texto | Estado | Candidatos (puntaje) |
|---|---|---|
| doña rosa | encontrado | Rosa Martínez (1.0), Luz Marina Ríos (0.5) |
| Rosita | encontrado | Rosa Martínez (1.0) |
| Don pedro | ambiguo | Pedro Gómez (1.0), Pedro Ruiz (1.0) |
| Luz | encontrado | Luz Marina Ríos (1.0) |
| Pedro | ambiguo | Pedro Gómez (1.0), Pedro Ruiz (1.0) |
| Carlos | no_encontrado | ninguno |
| arroz | encontrado | Arroz 500g (1.0) |
| aroz | encontrado | Arroz 500g (0.57) |
| panela | encontrado | Panela (1.0), Pan (unidad) (0.43) |
| pan | ambiguo | Pan (unidad) (1.0), Panela (0.75) |
| leche | encontrado | Leche 1L (1.0) |
| ron | no_encontrado | ninguno |

**Lectura de los resultados:**
- Los apodos funcionan (Rosita, doña rosa) y se tolera un error de ortografía (aroz).
- "Don pedro" corresponde a dos clientes distintos: el sistema no escoge, pregunta.
- "pan" puede ser pan o panela. Subimos el margen de 0.1 a 0.3 para que en ese caso pregunte en vez de escoger en silencio, porque aquí se maneja dinero. **Costo:** pregunta más veces, y lo aceptamos.
- Con los umbrales vigentes (0.4 y 0.3), la suite de `eval/` dio 100 % de exactitud en las ejecuciones exitosas (sección 7); los casos 06 (clientes no registrados) y 10 (nombre ambiguo) ejercitan justamente esta decisión.

## 6. Guardado determinista y altas

### 6.1 Guardado

**Decisión:** la IA nunca escribe en la base de datos. Solo propone; el tendero confirma y `app/transacciones.py` guarda tras validar las reglas en código.

**Reglas que rechazan un movimiento** (`app/validaciones.py`):
- fiado o abono sin cliente;
- abono con productos;
- monto vacío, cero o negativo (no lo calcula la IA: se informa la suma de los productos y decide el tendero);
- productos que no suman el monto escrito;
- cliente o producto inexistente.

**Garantías:**
- Todo se guarda en una sola transacción: o entra completo o no entra nada.
- Los importes usan `Decimal`, no `float`, para evitar errores de redondeo.
- El historial es inmutable en la BD (triggers contra UPDATE, DELETE y TRUNCATE): las correcciones son transacciones nuevas.
- El saldo no se almacena: se calcula en la vista `saldos` (fiados menos abonos), así no puede quedar desactualizado.

**Si el total escrito no cuadra con los productos**, el sistema copia lo escrito y avisa, en lugar de "corregir": lo que vale es lo que dice el cuaderno (caso dorado 07).

**Evidencia:** `python -m pruebas.test_guardado` (rechaza la suma mal hecha de Luz y la anotación sin total de Rosita).

### 6.2 Clientes y productos nuevos

**Decisión:** el alta de clientes, productos y apodos la hace siempre el tendero desde la pantalla de revisión. La IA nunca crea registros.

**Por qué no crear automáticamente:** un error de lectura o de ortografía crearía duplicados ("Rosita" y "Rosa") y partiría el saldo de una persona en dos.

**Protección contra duplicados** (`app/catalogo.py`): si el nombre se parece a uno existente (puntaje de 0.8 o más), se rechaza y se muestran los parecidos; solo se crea si el tendero confirma que es otra persona o producto.

**Apodos:** cuando el tendero asocia un nombre desconocido a un cliente existente, puede guardar el apodo (`agregar_alias`) para que la próxima vez se reconozca solo.

## 7. Línea base de evaluación

Se hicieron **dos mediciones** con el modelo `gemini-3.6-flash`. Cada ejecución corre el flujo real (lectura con la IA + búsqueda de clientes y productos en la BD) sobre los 10 casos dorados de `eval/casos/`.

| Cifra | Medición 1 · 2026-10-27 (10 ejecuciones) | Medición 2 · 2026-10-28 (30 ejecuciones, **solo 9 terminaron**) |
|---|---|---|
| Exactitud de movimientos | 100,0 % (24 de 24) | 100,0 % (29 de 29) |
| Latencia mediana | 20,1 s | 24,8 s |
| Costo mediano por hoja | sin medir (mediana de 6 679 tokens) | **US$ 0,01498** (mediana de 8 731 tokens) |
| Tasa de fallos | 10,0 % (1 de 10: timeout) | 70,0 % (21 de 30: **todos error 429 por cuota**) |

**Cifras que usamos como línea base:** exactitud 100 %, latencia mediana ≈ 25 s, costo ≈ US$ 0,015 por hoja (medición del 2026-10-28, sobre las 9 ejecuciones exitosas). Detalle por ejecución en `eval/resultados.json` y, para la medición incompleta, en `eval/resultados_2026-10-28_parcial.json`.

**Precios usados para el costo:** US$ 0,75 por millón de tokens de entrada y US$ 3,75 por millón de tokens de salida (los tokens de razonamiento cuentan como salida). Fuente: https://ai.google.dev/gemini-api/docs/pricing, consultada el 27/10/2026.

**Cómo se calcula cada cifra:**
- **Exactitud:** un movimiento es correcto si coinciden el tipo, el cliente (como lo ve el tendero) y el monto. Inventar movimientos de más también resta. Se calcula solo sobre las ejecuciones que terminaron sin error; los fallos van aparte.
- **Latencia:** segundos desde que llega la foto hasta tener los movimientos con clientes y productos resueltos, incluidos los reintentos. Mediana de las ejecuciones exitosas.
- **Costo:** tokens de entrada y salida por el precio por millón de tokens definido en `.env`. Mediana de las ejecuciones exitosas.
- **Tasa de fallos:** ejecuciones que terminaron en error (timeout, cuota, caída de la API o JSON inválido tras los reintentos).

**Lectura honesta de las cifras:**
- **La medición del 28/10 es incompleta y lo decimos claramente.** De las 30 ejecuciones, 21 fallaron con `429 RESOURCE_EXHAUSTED`: se agotó la cuota del **plan gratuito** (20 solicitudes por día para `gemini-3.6-flash`). Cada hoja usa más de una solicitud (el agente consulta herramientas y luego da la respuesta final), y los reintentos por 503 también cuentan. Esos 21 fallos son de cuota, **no del modelo**, así que la tasa de fallos de 70 % no describe la calidad del sistema.
- **La exactitud de 100 % excluye los fallos.** En la medición del 27/10, contando el caso fallido (01, 4 movimientos esperados) serían 24 de 28 (≈ 85,7 %). Reportamos las dos cifras para no inflar el resultado.
- **Los casos que sí terminaron cubren poco:** en el 28/10 solo se completaron los casos 01 (3 pasadas), 02 (3), 03 (2) y 05 (1). Los casos 04 y 06 a 10 no se pudieron medir ese día; la medición del 27/10 sí los cubre (todos con 100 %).
- **Ninguna ejecución necesitó reintento de formato** (0 % en ambas mediciones): con el prompt actual y temperatura 0, el JSON salió válido a la primera.

- **La latencia es la limitación principal del producto:** varía entre 5,2 s (hoja sin movimientos) y 38,7 s.

**Pendiente para una línea base completa:** Medición del 2026-10-28 (incompleta):** se corrieron 30 ejecuciones y solo 9 terminaron: las otras 21 fallaron con error 429 porque se agotó la cuota diaria del plan gratuito (20 solicitudes por día para `gemini-3.6-flash`). Esos fallos son de cuota, no del modelo. Sobre las 9 ejecuciones exitosas: exactitud 100 %, latencia mediana 24,8 s y costo mediano de US$ 0,01498 por hoja ≈ 8 731 tokens; precios US$ 0,75 / 3,75 por millón de tokens de entrada / salida, según https://ai.google.dev/gemini-api/docs/pricing, consultados el 27/10/2026**.

## 8. Retos reales y lecciones

| Reto | Qué pasó | Cómo lo resolvimos |
|---|---|---|
| **Gemini saturado (503) y plazos vencidos (504)** | En pruebas, Google respondió `503 UNAVAILABLE` ("high demand") y `504 DEADLINE_EXCEEDED`; la pantalla decía "Revisa la clave", que era engañoso. En la medición del 28/10 hubo 3 respuestas 503, y el reintento único absorbió 2 de ellas | Se distinguieron los casos: un reintento único tras 2 s ante 503 (solo si queda tiempo), mensaje propio "La IA está saturada" y timeout con mensaje claro |
| **Cuota del plan gratuito (429)** | Al correr la evaluación completa (30 ejecuciones) se agotó el límite de 20 solicitudes por día de `gemini-3.6-flash`: 21 de 30 ejecuciones fallaron. El agente usa más de una solicitud por hoja | La app responde 429 con mensaje claro y deja la traza del fallo.
| **Latencia** | Mediana de 20 a 25 s por hoja | `THINKING_LEVEL=LOW`, todas las consultas del agente en un mismo turno, última llamada sin herramientas |
| **Reintentos sin fin** | Cada reintento podía sumar otro timeout completo | `Presupuesto` compartido por foto: el tiempo y los tokens cubren *todos* los intentos |
| **La IA que "ayuda" de más** | Riesgo de que sume, corrija o reemplace nombres | El prompt prohíbe calcular totales y corregir; el código detecta la diferencia y avisa |
| **Nombres ambiguos ("Don Pedro")** | Dos clientes comparten apodo | Estado `ambiguo`: el sistema pregunta, no escoge |
| **Contratos JSON rotos** | Respuestas con ```` ```json ```` o texto extra | Se limpian las comillas de código; si no es JSON válido se fuerza la llamada final; si no cumple el contrato, se reintenta con los errores |


## 9. Fuera del MVP

- Inicio de sesión del tendero y varias tiendas (el MVP asume una sola tienda).
- Cola de trabajos o streaming para lecturas lentas (sección 3).
- Embeddings si el catálogo crece o se necesita entender sinónimos (sección 5).
- Compatibilidad con varios proveedores en producción: la capa está desacoplada, pero solo hay una implementación real (Gemini) más la simulada.
