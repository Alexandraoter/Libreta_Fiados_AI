# 📒 Libreta de Fiados Inteligente

El tendero toma una foto de su cuaderno de fiados. Una IA lee la letra manuscrita, el tendero revisa y confirma, y el sistema guarda todo en un historial contable que no se puede alterar.

**Curso:** Ingeniería de Aplicaciones con IA · Universidad Cooperativa de Colombia
**Equipo:** Vanesa Otero Molano, Samuel Escobar Acevedo, Javier Andrés Orozco

---

## 1. ¿Qué problema resuelve?

Las tiendas de barrio llevan los fiados (ventas a crédito) en un cuaderno: sumas incorrectas, nombres ambiguos ("Doña Rosa", "Rosita") y pérdida de información. Cambiarles el hábito a aplicaciones complejas no funciona.

**Nuestra solución:** el tendero sigue escribiendo igual. Solo fotografía la hoja y el sistema hace el resto.

## 2. Flujo de la aplicación

1. **Foto:** el tendero sube una imagen JPG o PNG (máximo 5 MB) de la hoja. Endpoint `POST /api/extraer`.
2. **Lectura con IA (Gemini):** el modelo lee la foto y propone los movimientos (ventas, fiados y abonos) en JSON. El backend valida ese JSON con Pydantic (`app/web/schemas.py`). Si no cumple el formato, vuelve a pedirle la lectura a la IA enviándole los errores encontrados.
3. **Identificación de clientes y productos:** el backend consulta la base de datos con herramientas de solo lectura (`buscar_cliente`, `buscar_producto`) y marca como advertencia lo que sea ambiguo o no exista.
4. **Revisión humana:** el tendero ve el resumen con las advertencias, corrige lo que haga falta (puede crear clientes, productos y apodos nuevos) y confirma.
5. **Guardado determinista:** `POST /api/confirmar` valida las reglas de negocio (sumas, rangos) y guarda toda la hoja en una sola transacción, o no guarda nada. El historial es inmutable: un trigger de PostgreSQL bloquea cualquier UPDATE o DELETE sobre las transacciones.

## 3. ¿Dónde interviene la IA y dónde no?

| Lo hace la IA (Gemini) | Lo hace código determinista |
|---|---|
| Leer la caligrafía de la foto | Validar el formato del JSON (Pydantic) |
| Convertir el texto en movimientos (JSON) | Verificar que las sumas cuadren |
| Anotar en `advertencias` lo que no se entiende | Buscar clientes y productos en la BD (similitud de texto) |
| | Reglas de negocio, guardado y saldos |

**La IA nunca escribe en la base de datos ni tiene acceso a ella.** Solo propone; el tendero decide y el backend valida.

## 4. Inicio rápido

### Prerrequisitos

- Docker (Docker Desktop o Docker Engine) con Docker Compose v2
- Una API Key de Google Gemini ([obtenerla en Google AI Studio](https://aistudio.google.com/apikey))
- Python 3.12 solo si vas a correr las pruebas fuera de Docker

### Pasos

**macOS, Linux o Git Bash en Windows:**

```bash
# 1. Entrar a la carpeta del proyecto
cd Libreta_Fiados_AI

# 2. Ejecutar el script (la primera vez crea .env y se detiene para que pegues tu clave)
./run.sh
```

**Windows (PowerShell):**

```powershell
cd Libreta_Fiados_AI
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

La primera vez, el script crea el archivo `.env` a partir de `.env.example` y se detiene. Abre `.env`, pega tu `GEMINI_API_KEY` y vuelve a ejecutar el mismo comando.

**Sin el script (cualquier sistema):**

```bash
cp .env.example .env        # en PowerShell: Copy-Item .env.example .env
# editar .env y pegar GEMINI_API_KEY
docker compose up --build
```

Cuando veas `Application startup complete`, abre **http://localhost:8000**.

La base de datos se crea sola la primera vez, con datos de ejemplo (4 clientes con apodos y 8 productos). Para detener la app: `Ctrl+C`. Para borrar la base de datos y empezar de cero: `docker compose down -v`.

### Variables de entorno (`.env`)

| Variable | Descripción | Valor en `.env.example` |
|---|---|---|
| `GEMINI_API_KEY` | Tu clave de Google Gemini | vacía |
| `MODEL_NAME` | Modelo de Gemini a usar | `gemini-3.6-flash` |
| `PROVEEDOR_IA` | `gemini` o `falso` (IA simulada para pruebas) | `gemini` |
| `DATABASE_URL` | Conexión a PostgreSQL para correr sin Docker. Con `docker compose` la define `docker-compose.yml` | `postgresql://fiados:fiados@localhost:5433/fiados` |
| `MAX_INTENTOS` | Veces que se le pide la lectura a la IA si su respuesta no cumple el formato | `3` |
| `TIMEOUT_SEGUNDOS` | Tiempo máximo de cada llamada a Gemini | `30` |
| `MAX_TOKENS` | Tope de tokens de salida por respuesta | `8192` |
| `FALSO_ESCENARIO` | Solo con `PROVEEDOR_IA=falso`: `ok`, `vacio`, `invalido`, `timeout`, `cuota` o `api` | `ok` (si no se define) |

### Probar sin gastar cuota de Gemini

En `.env` pon `PROVEEDOR_IA=falso` y elige un escenario, por ejemplo `FALSO_ESCENARIO=timeout`. Luego levanta con `docker compose up --build` (el script `run.sh` exige `GEMINI_API_KEY`, así que en este modo usa el comando directo). Sirve para ver en la interfaz cómo se comporta la app ante cada fallo.

## 5. IA utilizada

- **Proveedor y modelo:** Google Gemini, `gemini-3.6-flash` (configurable con `MODEL_NAME`).
- **Por qué:** recibe la imagen directamente y devuelve JSON en una sola llamada (`response_mime_type = application/json`, temperatura 0), sin un OCR aparte.
- **Patrón de integración:** en la misma petición. La respuesta llega en la misma llamada HTTP.
- **Capa desacoplada** (`app/ia/`):

| Archivo | Responsabilidad |
|---|---|
| `proveedor.py` | Interfaz: `leer_hoja(img, mime, correccion) → JSON crudo` |
| `gemini.py` | Implementación con Gemini. Es el único archivo que usa la librería `genai` |
| `falso.py` | IA simulada para pruebas, con los escenarios de fallo |
| `prompts.py` | Instrucciones a la IA, independientes del proveedor |
| `errores.py` | `FalloProveedor` (`timeout`, `cuota`, `api`) |
| `__init__.py` | `obtener_proveedor()`: elige el proveedor según `PROVEEDOR_IA` |

Cambiar de proveedor implica escribir una clase nueva con el mismo método y registrarla en `__init__.py`; el resto de la app no cambia.

## 6. Límites y control de la IA

| Límite | Cómo funciona |
|---|---|
| Reintentos | Máximo `MAX_INTENTOS` lecturas por foto. Cada reintento le envía a la IA los errores de validación del intento anterior |
| Timeout | `TIMEOUT_SEGUNDOS` por llamada a Gemini. Al vencerse, el usuario recibe un error 504 con mensaje claro |
| Tokens | `MAX_TOKENS` limita la longitud de cada respuesta |
| Tamaño de la foto | Solo JPG o PNG de hasta 5 MB |
| Confirmación humana | Nada se guarda sin que el tendero confirme en la pantalla. El endpoint `/api/confirmar` además tiene un modo `simular` que valida y deshace la transacción |

## 7. Herramientas de solo lectura

Están en `app/herramientas.py` y nunca escriben en la base de datos:

- `buscar_cliente(nombre)`: clientes parecidos al texto, comparando contra el nombre y los apodos.
- `buscar_producto(texto)`: productos parecidos del catálogo.

Ambas usan `word_similarity` de la extensión `pg_trgm` de PostgreSQL, con un puntaje mínimo de 0.4. El resultado es `encontrado`, `ambiguo` (varios candidatos parecidos; decide el tendero) o `no_encontrado`. El backend las ejecuta después de la lectura de la IA y su resultado se muestra en el panel de trazas. Por qué no usamos RAG: ver `docs/decisiones.md`.

## 8. Manejo de fallos

El usuario nunca ve un stack trace; siempre recibe un mensaje en español.

| Situación | Respuesta |
|---|---|
| La IA tarda más del límite | 504, "La IA tardó demasiado" |
| Se agota la cuota de Gemini | 429, "Se agotó el límite de uso de la IA" |
| Gemini no responde o la clave es inválida | 503, "No se pudo conectar con la IA" |
| La IA responde algo que no cumple el formato | Se reintenta con los errores; si persiste, 422 con una sugerencia de foto más clara |
| La foto no tiene movimientos | 422, "No encontré movimientos en esta foto" |
| `PROVEEDOR_IA` mal configurado | 503, "La IA no está configurada" |
| La base de datos no responde | La lectura de la foto sigue funcionando y la pantalla avisa que no pudo consultar clientes; al guardar, 503 y no se guarda nada |

## 9. Trazas

La respuesta de `/api/extraer` incluye una lista `trazas`, y la interfaz la muestra en el panel **"Trazas de la IA y las herramientas"**. Cada fila indica la herramienta, la entrada, el estado, el detalle y el tiempo en milisegundos: la lectura de la foto con Gemini y cada consulta de cliente o producto.

## 10. Pruebas

```bash
# Instalar las dependencias de desarrollo (incluye pytest)
pip install -r requirements-dev.txt

# Algunas pruebas consultan la base de datos: levantarla primero
docker compose up -d db

# Correr las pruebas desde la raíz del proyecto
python -m pytest pruebas -v
```

Las pruebas de `test_reintento.py` usan la IA simulada (`falso.py`): verifican los reintentos, la respuesta inválida, la hoja vacía y la traducción de cada fallo a su código HTTP, sin gastar cuota de Gemini.

## 11. Estructura del repositorio

```
README.md
docker-compose.yml     # base de datos + aplicación
Dockerfile
run.sh / run.ps1       # arranque con un solo comando
.env.example
requirements.txt
requirements-dev.txt   # requirements.txt + pytest (para las pruebas)
app/
  ia/                  # capa de IA desacoplada (sección 5)
  web/                 # FastAPI: main.py, schemas.py y la interfaz en static/
  herramientas.py      # buscar_cliente / buscar_producto (solo lectura)
  validaciones.py      # reglas de negocio
  transacciones.py     # guardado en una sola transacción
  catalogo.py          # altas de clientes, productos y apodos
  modelos.py, db.py
db/                    # esquema (01_schema.sql) y datos de ejemplo (02_seed.sql)
pruebas/
docs/decisiones.md     # decisiones técnicas y por qué
```

## 12. Decisiones técnicas

Ver [`docs/decisiones.md`](docs/decisiones.md).

## 13. Equipo y reparto

Vanesa Otero Molano, Samuel Escobar Acevedo y Javier Andrés Orozco. Áreas de trabajo: agente e integración con Gemini; aplicación e interfaz; datos, base de datos, validaciones y documentación.
