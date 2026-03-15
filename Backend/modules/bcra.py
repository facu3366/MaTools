"""
🏦 BCRA MODULE

Endpoints relacionados con el sistema financiero argentino
usando datos del Banco Central de la República Argentina.

Endpoint disponible:

GET /bcra/bancos
    → Ranking de bancos por:
        - Activos
        - Depósitos
        - Patrimonio Neto
        - Préstamos
"""

from fastapi import APIRouter, HTTPException
from typing import Optional
import os
import sys

# permitir importar desde carpeta raíz del proyecto
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from scrapers.bcra_scraper import get_bcra_bancos


# Router de FastAPI
router = APIRouter()


# ─────────────────────────────────────────────
# ENDPOINT
# ─────────────────────────────────────────────

@router.get("/bcra/bancos")
def bcra_bancos(top_n: Optional[int] = None):
    """
    Devuelve ranking del sistema financiero argentino
    usando datos públicos del BCRA.

    Parámetros:
        top_n → limita cantidad de bancos

    Ejemplo:
        /bcra/bancos
        /bcra/bancos?top_n=10
    """

    print(f"\n🏦 BCRA request — top_n={top_n}")

    try:

        resultado = get_bcra_bancos(top_n=top_n)

        if "error" in resultado:
            raise HTTPException(
                status_code=500,
                detail=resultado["error"]
            )

        return resultado

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo datos del BCRA: {str(e)}"
        )