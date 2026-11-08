CREATE ROLE app_fiados LOGIN PASSWORD :'clave';
GRANT CONNECT ON DATABASE fiados TO app_fiados;
GRANT USAGE ON SCHEMA public TO app_fiados;
GRANT SELECT ON clientes, alias_cliente, productos, importaciones,
                transacciones, transaccion_items, trazas_agente, saldos TO app_fiados;
GRANT INSERT ON clientes, alias_cliente, productos, importaciones,
                transacciones, transaccion_items, trazas_agente TO app_fiados;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_fiados;