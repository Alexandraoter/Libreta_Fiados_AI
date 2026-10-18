-- Datos de ejemplo para desarrollo y pruebas.
-- Los ids asumen una base de datos recién creada.

INSERT INTO clientes (nombre, telefono) VALUES
  ('Rosa Martínez',   '3001112233'),
  ('Pedro Gómez',     '3004445566'),
  ('Pedro Ruiz',      '3007778899'),
  ('Luz Marina Ríos', NULL);

INSERT INTO alias_cliente (cliente_id, alias) VALUES
  (1, 'Doña Rosa'), (1, 'Rosita'),
  (2, 'Don Pedro'), (2, 'Pedro G'),
  (3, 'Don Pedro'), (3, 'Pedro R'),
  (4, 'Luz'),       (4, 'Doña Luz');

INSERT INTO productos (nombre, precio_ref) VALUES
  ('Arroz 500g', 2800), ('Panela', 3500), ('Leche 1L', 4200),
  ('Huevos (unidad)', 700), ('Aceite 1L', 12500), ('Azúcar 1kg', 4800),
  ('Pan (unidad)', 500), ('Gaseosa 1.5L', 5500);

INSERT INTO transacciones (cliente_id, tipo, monto, fecha_movimiento, nota) VALUES
  (1, 'fiado', 8400, CURRENT_DATE - 3, '3 arroz'),
  (1, 'abono', 5000, CURRENT_DATE - 1, NULL),
  (2, 'fiado', 7700, CURRENT_DATE - 2, 'panela y leche');

INSERT INTO transaccion_items (transaccion_id, producto_id, cantidad, precio_unitario) VALUES
  (1, 1, 3, 2800),
  (3, 2, 1, 3500),
  (3, 3, 1, 4200);