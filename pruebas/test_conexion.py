from app.db import get_conn

with get_conn() as conn:
    version = conn.execute("SELECT version() AS v").fetchone()["v"]
    clientes = conn.execute("SELECT id, nombre FROM clientes ORDER BY id").fetchall()
    saldos = conn.execute("SELECT nombre, saldo FROM saldos ORDER BY cliente_id").fetchall()

print(version)
print("Clientes:", clientes)
print("Saldos:", saldos)
