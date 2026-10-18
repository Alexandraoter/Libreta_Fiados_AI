# 📒 Libreta de Fiados Inteligente

> El tendero toma una **foto** de su cuaderno de fiados. Una IA lee la
> letra manuscrita, el tendero **revisa y confirma**, y el sistema guarda
> todo en un historial contable que no se puede alterar.

**Curso:** Ingeniería de Aplicaciones con IA · Universidad Cooperativa de Colombia
**Equipo:** Vanesa Otero Molano, Samuel Escobar Acevedo, Javier Andrés Orozco

---

## 1. ¿Qué problema resuelve?

Las tiendas de barrio llevan los fiados (ventas a crédito) en un cuaderno:
sumas incorrectas, nombres ambiguos ("Doña Rosa", "Rosita") y pérdida de
información. Cambiarles el hábito a aplicaciones complejas no funciona.

**Nuestra solución:** el tendero sigue escribiendo igual. Solo fotografía
la hoja y el sistema hace el resto.

## 2. Flujo de la aplicación

1. **Foto:** el tendero sube la foto de la hoja del cuaderno.
2. **IA (Gemini):** extrae movimientos (ventas, fiados, abonos) y consulta
   la base de datos para identificar clientes y productos.
3. **Revisión humana:** el tendero ve un resumen con totales y saldos,
   corrige lo que haga falta y confirma.
4. **Backend determinista:** valida sumas, rangos y reglas de negocio, y
   guarda en un historial inmutable.

## 3. ¿Dónde interviene la IA y dónde no?

| Lo resuelve la IA (Gemini) | Lo resuelve código determinista |
|---|---|
| Leer la caligrafía de la foto | Validar que las sumas cuadren |
| Convertir texto a transacciones JSON | Rangos y reglas de negocio |
| Desambiguar nombres vía herramientas de **solo lectura** | Guardar en la base de datos |
| | Calcular saldos e historial |

**La IA nunca escribe en la base de datos.** Solo propone; el tendero
decide y el backend valida.

## 4. Inicio rápido (menos de 5 minutos)

### Prerrequisitos
- Docker Engine 24+ y Docker Compose v2
- Una API Key de Google Gemini ([obtenerla aquí](https://aistudio.google.com/apikey))
- (Solo para correr sin Docker) Python 3.11+

### Pasos
```bash
# 1. Descomprimir/clonar y entrar a la carpeta
cd libreta-fiados

# 2. Configurar credenciales
cp .env.example .env
#    Abrir .env y pegar tu GEMINI_API_KEY

# 3. Levantar todo
./run.sh
#    (equivale a: docker compose up --build)

# 4. Abrir en el navegador
#    http://localhost:8000
```

La base de datos se crea y se llena con datos de ejemplo
(clientes y catálogo) automáticamente.

### Variables de entorno (`.env`)
| Variable | Descripción |
|---|---|
| `GEMINI_API_KEY` | Tu clave de Google Gemini |
| `GEMINI_MODEL` | Modelo a usar (ej. `[gemini-xxx-flash]`) |
| `DATABASE_URL` | Ya viene configurada para Docker Compose |
| `MAX_ITERACIONES` | Límite de pasos del agente (por defecto 5) |
| `TIMEOUT_SEGUNDOS` | Tiempo máximo por solicitud (por defecto 30) |
| `MAX_TOKENS` | Tope de tokens de salida (por defecto 1024) |

## 5. IA utilizada

- **Proveedor y modelo:** Google Gemini `[modelo exacto]`
- **Por qué:** [1 línea cada una] entrada multimodal (imagen) en una sola
  llamada · latencia baja · costo por token bajo · tool calling
  estructurado · capa gratuita para desarrollo.
- **Patrón de integración:** In-request (la respuesta llega en la misma
  petición HTTP).
- **Capa desacoplada:** `app/ia/proveedor.py` define la interfaz;
  `app/ia/gemini.py` la implementa. Cambiar de proveedor no toca el resto.

## 6. Control del agente (4 límites activos)

1. **Iteraciones máximas** por solicitud
2. **Timeout** global
3. **Tope de tokens** de salida
4. **Confirmación humana** obligatoria antes de guardar

## 7. Herramientas del agente (solo lectura)
- `buscar_cliente(nombre)`: coincidencias aproximadas de clientes
- `buscar_producto(texto)`: coincidencias en el catálogo
- `[otra]`

## 8. Manejo de fallos
Timeout, respuesta inválida de la IA y caída de la API muestran mensajes
claros al usuario, sin stack traces. Ver `docs/decisiones.md`.

## 9. Evaluación y trazas
- Casos dorados: carpeta `eval/` → `python eval/run.py`
- Línea base (mediana, fecha): `docs/decisiones.md`
- Trazas de herramientas visibles en la interfaz (panel "Trazas").

## 10. Estructura del repositorio
```
README.md
docker-compose.yml
run.sh
.env.example
app/            # backend (FastAPI), agente, validaciones
frontend/       # interfaz web
db/             # esquema y datos semilla
eval/           # casos dorados y medición
docs/decisiones.md
```

## 11. Prueba del compañero
Probado por [Nombre] el [fecha] en un equipo limpio: levantó en [X] min.

## 12. Equipo y responsabilidades
| Integrante | Área principal |
|---|---|
| [Nombre 1] | Agente e integración con Gemini |
| [Nombre 2] | Frontend y manejo de fallos |
| [Nombre 3] | Datos, Docker, evaluación y documentación |
