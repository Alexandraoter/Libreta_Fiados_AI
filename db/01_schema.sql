-- =====================================================================
-- Esquema de la Libreta de Fiados Inteligente (PostgreSQL 16)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Clientes: no se borran, se desactivan para conservar el historial
CREATE TABLE clientes (
  id         SERIAL PRIMARY KEY,
  nombre     TEXT NOT NULL,
  telefono   TEXT,
  activo     BOOLEAN NOT NULL DEFAULT TRUE,
  creado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Apodos con que el tendero escribe a cada cliente
-- (dos clientes pueden compartir un apodo, como "Don Pedro")
CREATE TABLE alias_cliente (
  id          SERIAL PRIMARY KEY,
  cliente_id  INT  NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  alias       TEXT NOT NULL,
  UNIQUE (cliente_id, alias)
);

-- Catálogo de productos
CREATE TABLE productos (
  id          SERIAL PRIMARY KEY,
  nombre      TEXT NOT NULL UNIQUE,
  precio_ref  NUMERIC(12,2) NOT NULL CHECK (precio_ref >= 0),
  activo      BOOLEAN NOT NULL DEFAULT TRUE
);

-- Cada foto de la libreta que se procesa
CREATE TABLE importaciones (
  id             SERIAL PRIMARY KEY,
  archivo        TEXT,
  estado         TEXT NOT NULL DEFAULT 'pendiente'
                 CHECK (estado IN ('pendiente','confirmada','rechazada')),
  creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmada_en  TIMESTAMPTZ
);

-- Movimientos de dinero: venta (contado), fiado (crédito), abono (pago de deuda)
CREATE TABLE transacciones (
  id                SERIAL PRIMARY KEY,
  importacion_id    INT REFERENCES importaciones(id),
  cliente_id        INT REFERENCES clientes(id),
  tipo              TEXT NOT NULL CHECK (tipo IN ('venta','fiado','abono')),
  monto             NUMERIC(12,2) NOT NULL CHECK (monto > 0),
  fecha_movimiento  DATE NOT NULL DEFAULT CURRENT_DATE,
  nota              TEXT,
  creado_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT chk_cliente_requerido
    CHECK (tipo = 'venta' OR cliente_id IS NOT NULL)
);

-- Productos de cada transacción. precio_unitario es el precio del día de la venta
CREATE TABLE transaccion_items (
  id               SERIAL PRIMARY KEY,
  transaccion_id   INT NOT NULL REFERENCES transacciones(id),
  producto_id      INT NOT NULL REFERENCES productos(id),
  cantidad         NUMERIC(10,2) NOT NULL CHECK (cantidad > 0),
  precio_unitario  NUMERIC(12,2) NOT NULL CHECK (precio_unitario >= 0),
  subtotal         NUMERIC(12,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED
);

-- Cada llamada a herramienta que hace la IA (para mostrar trazas en la demo)
CREATE TABLE trazas_agente (
  id              SERIAL PRIMARY KEY,
  importacion_id  INT REFERENCES importaciones(id),
  paso            INT NOT NULL,
  herramienta     TEXT NOT NULL,
  entrada         JSONB,
  salida          JSONB,
  duracion_ms     INT,
  error           TEXT,
  creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices
CREATE INDEX idx_transacciones_cliente  ON transacciones(cliente_id);
CREATE INDEX idx_transacciones_import   ON transacciones(importacion_id);
CREATE INDEX idx_items_transaccion      ON transaccion_items(transaccion_id);
CREATE INDEX idx_trazas_importacion     ON trazas_agente(importacion_id);
CREATE INDEX idx_clientes_nombre_trgm   ON clientes      USING gin (nombre gin_trgm_ops);
CREATE INDEX idx_alias_trgm             ON alias_cliente USING gin (alias  gin_trgm_ops);
CREATE INDEX idx_productos_nombre_trgm  ON productos     USING gin (nombre gin_trgm_ops);

-- Historial inmutable: nadie puede modificar ni borrar transacciones
CREATE FUNCTION bloquear_cambios() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'La tabla % es inmutable: operacion % bloqueada', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER transacciones_inmutable
  BEFORE UPDATE OR DELETE ON transacciones
  FOR EACH ROW EXECUTE FUNCTION bloquear_cambios();

CREATE TRIGGER transacciones_sin_truncate
  BEFORE TRUNCATE ON transacciones
  FOR EACH STATEMENT EXECUTE FUNCTION bloquear_cambios();

CREATE TRIGGER items_inmutable
  BEFORE UPDATE OR DELETE ON transaccion_items
  FOR EACH ROW EXECUTE FUNCTION bloquear_cambios();

CREATE TRIGGER items_sin_truncate
  BEFORE TRUNCATE ON transaccion_items
  FOR EACH STATEMENT EXECUTE FUNCTION bloquear_cambios();

-- Vista de saldos: el saldo se calcula, no se guarda (fiados menos abonos)
CREATE VIEW saldos AS
SELECT c.id AS cliente_id,
       c.nombre,
       COALESCE(SUM(CASE t.tipo
                      WHEN 'fiado' THEN  t.monto
                      WHEN 'abono' THEN -t.monto
                      ELSE 0 END), 0) AS saldo
FROM clientes c
LEFT JOIN transacciones t ON t.cliente_id = c.id
GROUP BY c.id, c.nombre;