import sqlite3
from datetime import datetime

DB_PATH = "dealdesk.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bcra_bancos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        banco TEXT,
        activos REAL,
        depositos REAL,
        patrimonio REAL,
        prestamos REAL,
        fecha_reporte TEXT,
        fecha_scraping TEXT
    )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# INSERT
# ─────────────────────────────────────────────

def save_bcra_data(data):

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
        VALUES (?, ?, ?, ?, ?, ?, ?)
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


# ─────────────────────────────────────────────
# GET
# ─────────────────────────────────────────────

def get_bcra_data():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM bcra_bancos")

    rows = cursor.fetchall()

    conn.close()

    return [
        {
            "banco": r[1],
            "activos": r[2],
            "depositos": r[3],
            "patrimonio": r[4],
            "prestamos": r[5],
            "fecha_reporte": r[6],
            "fecha_scraping": r[7]
        }
        for r in rows
    ]