# 📒 Libreta de Fiados Inteligente

El tendero toma una foto de su cuaderno de fiados. Una IA lee la letra manuscrita, el tendero revisa y confirma, y el sistema guarda todo en un historial contable que no se puede alterar.

**Curso:** Ingeniería de Aplicaciones con IA · Universidad Cooperativa de Colombia
**Equipo:** Vanesa Otero Molano, Samuel Escobar Acevedo, Javier Andrés Orozco

---

## 1. ¿Qué problema resuelve?

Las tiendas de barrio llevan los fiados (ventas a crédito) en un cuaderno: sumas incorrectas, nombres ambiguos ("Doña Rosa", "Rosita") y pérdida de información. Cambiarles el hábito a aplicaciones complejas no funciona.

**Nuestra solución:** el tendero sigue escribiendo igual. Solo fotografía la hoja y el sistema hace el resto.

## 2. Flujo de la aplicación

1. **Foto:** el tendero sube una imagen JPG o PNG (máximo 5 MB). Endpoint `POST /api/extraer`.
2. **Lectura con IA (Gemini):** el modelo lee la foto y, antes de responder, puede consultar la base de datos con dos herramientas de solo lectura (`buscar_cliente`, `buscar_producto`) para confirmar lo que leyó ("aroz" frente a "arroz"). Devuelve los movimientos (ventas, fiados y abonos) en JSON.
3. **Validación determinista:** el backend valida el JSON con Pydantic (`app/web/schemas.py`) y calcula advertencias (suma que no cuadra, falta el cliente, falta el total). Si el JSON no cumple el formato, vuelve a pedirle la lectura a la IA enviándole los errores.
4. **Identificación de clientes y productos:** aparte de lo que consultó la IA, el backend resuelve cada cliente y producto en la base de datos y marca como advertencia lo ambiguo o inexistente. **El resultado del backend es el que manda.**
5. **Revisión humana:** el tendero ve el resumen con las advertencias, corrige lo que haga falta (puede crear clientes, productos y apodos nuevos) y confirma.
6. **Guardado determinista:** `POST /api/confirmar` valida las reglas de negocio y guarda toda la hoja en **una sola transacción**, o no guarda nada. El historial es inmutable: un trigger de PostgreSQL bloquea cualquier UPDATE, DELETE o TRUNCATE sobre las transacciones.

## 3. ¿Dónde interviene la IA y dónde no?

| Lo hace la IA (Gemini) | Lo hace código determinista |
|---|---|
| Leer la caligrafía de la foto | Validar el formato del JSON (Pydantic) |
| Convertir el texto en movimientos (JSON) | Verificar que las sumas cuadren |
| Decidir qué cliente/producto consultar con sus 2 herramientas | Ejecutar esas consultas (SQL con `pg_trgm`, solo lectura) |
| Anotar en `advertencias` lo que no se entiende | Resolver clientes y productos, reglas de negocio, guardado y saldos |

**La IA nunca escribe en la base de datos.** Solo puede *consultar* clientes y productos mediante dos herramientas de solo lectura, y su respuesta es una propuesta: el tendero decide y el backend valida. La IA tampoco calcula totales: si la libreta no trae el total, devuelve `null`.

## 4. Inicio rápido

### Prerrequisitos

| Componente | Versión |
|---|---|
| Docker Desktop o Docker Engine | con **Docker Compose v2** (`docker compose version`) |
| Python (dentro de la imagen) | 3.11 (`python:3.11-slim`, ya viene en el `Dockerfile`) |
| PostgreSQL (dentro de Docker) | 16 (`postgres:16`) |
| Python en tu máquina | 3.11 o superior, **solo** para correr pruebas o `eval/` fuera de Docker |
| API Key de Google Gemini | [obtenerla en Google AI Studio](https://aistudio.google.com/apikey). Ver la nota sobre la cuota del plan gratuito más abajo |

Se necesita conexión a internet (la app llama a la API de Gemini). El ZIP **no incluye ninguna clave**: cada quien pone la suya.

### Pasos

**macOS, Linux o Git Bash en Windows:**

```bash
cd Libreta_Fiados_AI
bash run.sh        # (o ./run.sh si el archivo tiene permiso de ejecución)
```

**Windows (PowerShell):**

```powershell
cd Libreta_Fiados_AI
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

La primera vez, el script crea `.env` a partir de `.env.example` y se detiene. Abre `.env`, pega tu `GEMINI_API_KEY` y vuelve a ejecutar el mismo comando.

**Sin el script (cualquier sistema):**

```bash
cp .env.example .env        # en PowerShell: Copy-Item .env.example .env
# editar .env y pegar GEMINI_API_KEY
docker compose up --build
```

Cuando veas `Application startup complete`, abre **http://localhost:8000**.

La base de datos se crea sola la primera vez con `db/01_schema.sql` (esquema) y `db/02_seed.sql` (datos de ejemplo: 4 clientes con apodos, 8 productos y 3 transacciones). Para detener la app: `Ctrl+C`. Para borrar la base de datos y empezar de cero: `docker compose down -v`.



### Variables de entorno (`.env`)

Todas están en `.env.example`. Solo `GEMINI_API_KEY` es obligatoria; el resto tiene un valor por defecto.

| Variable | Descripción | Valor en `.env.example` |
|---|---|---|
| `GEMINI_API_KEY` | Tu clave de Google Gemini (vacía = la app responde 503 "La IA no está configurada") | vacía |
| `DATABASE_URL` | Conexión a PostgreSQL para correr **sin** Docker. Con `docker compose` la define `docker-compose.yml` | `postgresql://fiados:fiados@localhost:5433/fiados` |
| `PROVEEDOR_IA` | `gemini` o `falso` (IA simulada para pruebas) | `gemini` |
| `MODEL_NAME` | Modelo de Gemini | `gemini-3.6-flash` |
| `THINKING_LEVEL` | Esfuerzo de razonamiento: `MINIMAL`, `LOW`, `MEDIUM`, `HIGH` o vacío | `LOW` |
| `MAX_INTENTOS` | Veces que se pide la lectura si la respuesta no cumple el formato | `3` |
| `TIMEOUT_SEGUNDOS` | Tiempo máximo de **cada** llamada a Gemini | `30` |
| `TIMEOUT_TOTAL_SEGUNDOS` | Tiempo máximo **total** de una foto (reintentos y vueltas del agente). `0` = sin tope | `60` |
| `MAX_TOKENS` | Tope de tokens de salida por respuesta | `8192` |
| `MAX_TOKENS_ACUMULADOS` | Tope de tokens **sumados** de todas las llamadas de una foto. `0` = sin tope | `50000` |
| `MAX_ITERACIONES` | Máximo de llamadas a Gemini por lectura (la última va sin herramientas). `1` = sin herramientas | `4` |
| `PRECIO_ENTRADA_USD_M`, `PRECIO_SALIDA_USD_M` | Solo para `eval/`: precio en USD por millón de tokens, para calcular el costo | vacías |
| `FALSO_ESCENARIO` | Solo con `PROVEEDOR_IA=falso`: `ok`, `vacio`, `invalido`, `timeout`, `cuota` o `api` | comentada (`ok`) |

### Probar sin gastar cuota de Gemini

En `.env` pon `PROVEEDOR_IA=falso` y elige un escenario, por ejemplo `FALSO_ESCENARIO=timeout`. Luego levanta con `docker compose up --build` (los scripts `run.sh` y `run.ps1` exigen `GEMINI_API_KEY`, así que en este modo usa el comando directo). Sirve para ver en la interfaz cómo se comporta la app ante cada fallo.

### ⚠️ Cuota del plan gratuito de Gemini

El plan gratuito de Google limita las solicitudes por día (en nuestra prueba del 2026-10-28, **20 por día** para `gemini-3.6-flash`). Cada foto puede usar varias solicitudes (el agente consulta clientes y productos y luego da la respuesta final), así que con una clave gratuita se alcanzan unas pocas hojas al día. Si se agota, la app responde **429** con el mensaje "Se agotó el límite de uso de la IA" y deja la traza del fallo. Soluciones: esperar a que se reinicie la cuota, usar una clave de un proyecto con facturación activa, o probar con `PROVEEDOR_IA=falso`.

### Prueba del compañero

Un compañero que no participó en el proyecto descargó el ZIP, siguió esta sección al pie de la letra y la aplicación levantó sin ayuda.

| Dato | Valor |
|---|---|
| Quién la hizo | **Alexandra Merchan Pantoja** |
| Fecha | ** 2026-10-29** |
| Sistema operativo | ** Windows ** |
| Tiempo hasta ver la app en `localhost:8000` | **Latencia de 5min 15s** |
| Problemas encontrados y cómo se corrigieron | **ninguno para ella** |

## 5. IA utilizada

- **Proveedor y modelo:** Google Gemini, `gemini-3.6-flash` (configurable con `MODEL_NAME`), con el SDK `google-genai`.
- **Por qué este modelo** (detalle en `docs/decisiones.md`, sección 2):
  - *Entrada de imagen nativa:* lee la foto directamente, sin un OCR aparte que sumaría otra pieza y otro punto de fallo.
  - *Salida estructurada:* devuelve JSON en la llamada final (`response_mime_type = application/json`, temperatura 0).
  - *Llamado de herramientas:* soporta function calling, que es lo que usa el agente para consultar clientes y productos.
  - *Costo de la decisión:* la latencia es alta (mediana de 20 a 25 s por hoja en nuestras mediciones, ver sección 9) y cada hoja cuesta ≈ US$ 0,015 con los precios del 2026-10-27. La latencia la reducimos con `THINKING_LEVEL=LOW`.
- **Patrón de integración:** en la misma petición (*in-request*). La respuesta llega en la misma llamada HTTP; no usamos streaming ni colas.
- **Capa desacoplada** (`app/ia/`):

| Archivo | Responsabilidad |
|---|---|
| `proveedor.py` | Interfaz `ProveedorIA`: `leer_hoja(img, mime, correccion, trazas, presupuesto) → JSON crudo` |
| `gemini.py` | Implementación con Gemini y bucle del agente. **Es el único archivo que importa `genai`** |
| `herramientas_ia.py` | Declaraciones de las 2 herramientas (formato de Gemini) y sus ejecutores de solo lectura |
| `presupuesto.py` | Tiempo total y tokens acumulados de una lectura |
| `falso.py` | IA simulada para pruebas, con los escenarios de fallo |
| `prompts.py` | Instrucciones a la IA, independientes del proveedor |
| `errores.py` | `FalloProveedor` con códigos `timeout`, `cuota`, `tokens`, `api` |
| `__init__.py` | `obtener_proveedor()`: elige el proveedor según `PROVEEDOR_IA` |

Cambiar de proveedor implica escribir una clase nueva con el mismo método y registrarla en `__init__.py`; el resto de la app no cambia.

## 6. Límites y control de la IA

La lectura es un pequeño agente (bucle de herramientas) con límites en cada nivel:

| Límite | Cómo funciona |
|---|---|
| **Iteraciones** | `MAX_ITERACIONES` (4): máximo de llamadas a Gemini por lectura. La **última** va siempre sin herramientas y con JSON obligatorio, así que el bucle termina con una respuesta estructurada aunque el modelo siguiera pidiendo consultas |
| **Timeout** | `TIMEOUT_SEGUNDOS` (30) por llamada y `TIMEOUT_TOTAL_SEGUNDOS` (60) para toda la foto. El timeout de cada llamada nunca pasa del tiempo total que queda. Al vencerse: error 504 |
| **Tokens** | `MAX_TOKENS` (8192) por respuesta y `MAX_TOKENS_ACUMULADOS` (50 000) sumando todas las llamadas. Si se supera, no se empieza otra llamada: error 422 |
| **Confirmación humana** | Nada se guarda sin que el tendero confirme. `/api/confirmar` además tiene un modo `simular` (activo por defecto en la API) que valida y deshace la transacción; guardar de verdad pide una confirmación adicional en pantalla |
| Reintentos de formato | Máximo `MAX_INTENTOS` lecturas por foto; cada reintento le envía a la IA los errores de validación del anterior |
| Saturación (503) | Un único reintento tras 2 s, solo si queda tiempo en el presupuesto |
| Tamaño de la foto | Solo JPG o PNG de hasta 5 MB |

## 7. Herramientas del agente (solo lectura)

Declaradas en `app/ia/herramientas_ia.py` y ejecutadas con `app/herramientas.py`. Nunca escriben en la base de datos:

- `buscar_cliente(nombre)`: clientes parecidos al texto, comparando contra el nombre y los apodos.
- `buscar_producto(texto)`: productos parecidos del catálogo.

Ambas usan `word_similarity` de la extensión `pg_trgm` de PostgreSQL, con un puntaje mínimo de 0,4. El resultado es `encontrado`, `ambiguo` (varios candidatos parecidos; decide el tendero) o `no_encontrado`. A la IA solo se le devuelve el estado y los nombres con su puntaje: **sin ids y sin precios**, para que no "corrija" con ellos lo que el tendero escribió. Si una herramienta falla (por ejemplo, la BD está caída), la lectura continúa sin ella. Por qué no usamos RAG: ver `docs/decisiones.md`, sección 5.

## 8. Manejo de fallos y trazas

El usuario nunca ve un stack trace; siempre recibe un mensaje en español.

| Situación | Respuesta |
|---|---|
| La IA tarda más del límite (por llamada o en total) | 504, "La IA tardó demasiado" |
| Se agota la cuota de Gemini (puede ser la cuota **diaria** del plan gratuito) | 429, "Se agotó el límite de uso de la IA" |
| Gemini está saturado (503 de Google) | Se reintenta una vez; si persiste, 503, "La IA está saturada en este momento" |
| Gemini no responde o la clave es inválida | 503, "No se pudo conectar con la IA" |
| Se supera el tope de tokens acumulados | 422, "Esta hoja consumió más IA de la permitida" |
| La IA responde algo que no cumple el formato | Se reintenta con los errores; si persiste, 422 con una sugerencia de foto más clara |
| La foto no tiene movimientos | 422, "No encontré movimientos en esta foto" |
| Archivo que no es JPG/PNG, vacío o de más de 5 MB | 400 / 400 / 413 con mensaje claro |
| `PROVEEDOR_IA` o un límite mal configurado | 503, "La IA no está configurada" |
| La base de datos no responde | La lectura de la foto sigue funcionando y la pantalla avisa que no pudo consultar clientes; al guardar, 503 y no se guarda nada |

**Trazas:** la respuesta de `/api/extraer` incluye una lista `trazas` (también cuando falla), y la interfaz la muestra en el panel **"Trazas de la IA y las herramientas"**. Cada fila indica la herramienta, la entrada, el estado, el detalle y los milisegundos: la lectura con Gemini, cada consulta del agente (`buscar_cliente (agente)`, `buscar_producto (agente)`), cada intento inválido (`validar_hoja`) y la resolución final en la BD.

## 9. Evaluación (`eval/`)

Suite de **10 casos dorados**: fotos reales de hojas (`eval/casos/*.jpg`) con la respuesta correcta escrita a mano (`eval/casos/casos.json`). Cubren fiados, abonos con sinónimos, ventas de contado, hoja vacía, clientes no registrados, totales que no cuadran, líneas tachadas, fechas y nombres ambiguos.

```bash
# con la BD levantada (docker compose up -d db) y las dependencias de desarrollo instaladas
python -m eval.run --validar            # solo revisa casos.json, no llama a la IA
python -m eval.run --repeticiones 3     # corre los casos 3 veces (la mediana sale más estable)
```

Escribe `eval/resultados.json` (detalle por ejecución) y `eval/linea_base.md` (las 4 cifras). Para que el costo salga medido, define `PRECIO_ENTRADA_USD_M` y `PRECIO_SALIDA_USD_M` en `.env` antes de correrlo (nosotros usamos US$ 0,75 y US$ 3,75 por millón de tokens, según https://ai.google.dev/gemini-api/docs/pricing, consultada el 2026-10-27).



Resumen de la línea base (medición del 2026-10-28, sobre las ejecuciones que terminaron): exactitud 100 %, latencia mediana ≈ 25 s y costo mediano ≈ US$ 0,015 por hoja. Esa medición quedó **incompleta** porque se agotó la cuota gratuita (9 de 30 ejecuciones exitosas). La medición del 2026-10-27 y el análisis completo están en `docs/decisiones.md`, sección 7.

## 10. Pruebas

```bash
pip install -r requirements-dev.txt     # requirements.txt + pytest
docker compose up -d db                 # algunas pruebas consultan la base de datos
python -m pytest pruebas -v
```

Las pruebas usan la IA simulada (`falso.py`) o un cliente de Gemini sustituido, así que **no gastan cuota**. Cubren, entre otras cosas: los límites del agente (iteraciones, tiempo total, tokens acumulados), los reintentos, la traducción de cada fallo a su código HTTP, la herramienta caída o inventada por el modelo, el guardado transaccional y la búsqueda de clientes y productos.

## 11. Estructura del repositorio

```
README.md
docker-compose.yml     # base de datos (db) + aplicación (app)
Dockerfile
run.sh / run.ps1       # arranque con un solo comando
.env.example
requirements.txt
requirements-dev.txt   # requirements.txt + pytest
app/
  ia/                  # capa de IA desacoplada (sección 5)
  web/                 # FastAPI: main.py, schemas.py y la interfaz en static/
  herramientas.py      # buscar_cliente / buscar_producto (solo lectura)
  validaciones.py      # reglas de negocio
  transacciones.py     # guardado en una sola transacción
  catalogo.py          # altas de clientes, productos y apodos
  modelos.py, db.py
db/                    # esquema (01_schema.sql) y datos de ejemplo (02_seed.sql)
eval/                  # casos dorados, run.py, resultados.json y linea_base.md
pruebas/               # pruebas con pytest
docs/decisiones.md     # decisiones técnicas, datos y línea base
```

## 12. Decisiones técnicas

Ver [`docs/decisiones.md`](docs/decisiones.md): arquitectura, proveedor y modelo, agente y límites, herramientas, datos (por qué no RAG), guardado, retos reales y línea base.

## 13. Equipo y reparto

Vanesa Otero Molano, Samuel Escobar Acevedo y Javier Andrés Orozco. Áreas de trabajo: agente e integración con Gemini; aplicación e interfaz; datos, base de datos, validaciones y documentación.
