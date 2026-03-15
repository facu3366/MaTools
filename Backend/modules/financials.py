from fastapi import APIRouter
import pathlib
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from comps_automatico import UNIVERSE

router = APIRouter()

# ─────────────────────────────────────────────
# AUTOCOMPLETE — catálogo de empresas
# ─────────────────────────────────────────────

@router.get("/api/empresas")
def get_empresas():
    """
    Devuelve el catálogo de empresas para autocomplete del frontend.

    Busca empresas.json en varias rutas posibles (local, Railway, etc).
    Si no encuentra el JSON, genera un catálogo desde UNIVERSE.
    """

    posibles_rutas = [
        "Data/empresas.json",
        "FrontEnd/Data/empresas.json",
        "../FrontEnd/Data/empresas.json",
        "empresas.json",
    ]

    for ruta in posibles_rutas:
        try:
            path = pathlib.Path(ruta)

            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))

                print(f"✅ empresas.json cargado desde: {ruta} ({len(data)} empresas)")

                return data

        except Exception:
            continue

    # fallback automático si no existe JSON
    print("⚠️ empresas.json no encontrado — generando desde UNIVERSE")

    data = []

    for sector, tickers in UNIVERSE.items():
        for t in tickers:
            data.append({
                "name": t,
                "ticker": t,
                "sector": sector,
                "alias": [t.lower()]
            })

    return data