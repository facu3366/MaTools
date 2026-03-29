import psycopg2
import os
from datetime import datetime


# conexión a postgres usando variable de railway
def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bcra_bancos (
            id SERIAL PRIMARY KEY,
            banco TEXT,
            activos REAL,
            depositos REAL,
            patrimonio REAL,
            prestamos REAL,
            fecha_reporte TEXT,
            fecha_scraping TEXT
        )
        """)

        # 👉 NUEVA TABLA PARA CACHE
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            cache_key TEXT PRIMARY KEY,
            data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """)

        conn.commit()
        conn.close()
        print("✅ DB conectada + cache ready")

    except Exception as e:
        print(f"⚠️ DB no disponible (local mode): {e}")


# ─────────────────────────────────────────────
# INSERT 
# ─────────────────────────────────────────────

def save_bcra_data(data):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM bcra_bancos")

        for b in data["bancos"]:

            cursor.execute("""
            INSERT INTO bcra_bancos (
                banco,
                activos,
                depositos,
                patrimonio,
                prestamos,
                fecha_reporte,
                fecha_scraping
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                b.get("Banco"),
                b.get("Activos"),
                b.get("Depositos"),
                b.get("Patrimonio Neto"),
                b.get("Prestamos"),
                data.get("fecha_reporte"),
                data.get("fecha_scraping")
            ))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ save_bcra_data failed (no DB): {e}")


# ─────────────────────────────────────────────
# GET
# ─────────────────────────────────────────────

def get_bcra_data():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM bcra_bancos")

        rows = cursor.fetchall()

        conn.close()

        return [
            {
                "Banco": r[1],
                "Activos": r[2],
                "Depositos": r[3],
                "Patrimonio Neto": r[4],
                "Prestamos": r[5],
                "fecha_reporte": r[6],
                "fecha_scraping": r[7]
            }
            for r in rows
        ]
    except Exception as e:
        print(f"⚠️ get_bcra_data failed (no DB): {e}")
        return []