# Decisiones técnicas

## 1. Búsqueda de clientes y productos: SQL aproximado, no RAG

**Decisión:** los nombres que escribe el tendero ("doña rosa", "aroz") se
resuelven con búsqueda aproximada en PostgreSQL (extensión `pg_trgm`, función
`word_similarity`). No usamos RAG ni embeddings.

**Por qué:**
- Los datos son pocos y estructurados: clientes (con apodos) y un catálogo de
  productos. En una tienda de barrio son cientos de filas, no miles de documentos.
- Es determinista y auditable: la misma entrada da siempre el mismo resultado y
  el puntaje se puede explicar.
- No agrega costo ni latencia de una API: la consulta corre dentro de la propia BD.
- Es seguro: la IA solo consulta con herramientas de solo lectura y, cuando hay
  duda, devuelve candidatos para que decida el tendero.

**Limitación conocida:** la búsqueda por trigramas no entiende sinónimos
("refresco" y "gaseosa"). Si el catálogo creciera a miles de productos o
necesitáramos esa comprensión, evaluaríamos embeddings.

**Cómo decide el sistema** (`app/herramientas.py`):
- `UMBRAL = 0.4`: puntaje mínimo (0 a 1) para considerar un candidato.
- `DIFERENCIA_AMBIGUA = 0.3`: si el primer candidato no supera al segundo por al
  menos este margen, el estado es `ambiguo` y decide el tendero.
- Estados posibles: `encontrado`, `ambiguo`, `no_encontrado`.

**Resultados** (`python -m pruebas.test_herramientas`, fecha: [2026-10-20]):

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
- "pan" puede ser pan o panela. Subimos el margen de 0.1 a 0.3 para que en ese
  caso pregunte en vez de escoger en silencio, porque aquí se maneja dinero.
- Los umbrales se volverán a ajustar con los casos de la carpeta `eval/`.




## 2. Guardado determinista

**Decisión:** la IA nunca escribe en la base de datos. Solo propone; el tendero
confirma y `app/transacciones.py` guarda tras validar las reglas en código.

**Reglas que rechazan un movimiento** (`app/validaciones.py`):
- fiado o abono sin cliente;
- abono con productos;
- monto vacío, cero o negativo (no se calcula por la IA: se informa la suma de
  los productos y decide el tendero);
- productos que no suman el monto escrito;
- cliente o producto inexistente.

**Garantías:**
- Todo se guarda en una sola transacción: o entra completo o no entra nada.
- Los importes usan `Decimal`, no `float`, para evitar errores de redondeo.
- El historial es inmutable en la BD (triggers): las correcciones son
  transacciones nuevas.
- El saldo no se almacena: se calcula en la vista `saldos` (fiados menos abonos).

**Evidencia:** `python -m pruebas.test_guardado` (rechaza la suma mal hecha de
Luz y la anotación sin total de Rosita).