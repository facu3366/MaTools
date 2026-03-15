from fastapi import APIRouter, HTTPException
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from scrapers.bcra_scraper import get_bcra_bancos

router = APIRouter()

# ─────────────────────────────────────────────
# BCRA — Rankings sistema financiero argentino
# ─────────────────────────────────────────────

@router.get("/bcra/bancos")
def bcra_bancos(top_n: int = None):
    """
    Rankings del sistema financiero argentino (BCRA).

    Devuelve:
    - Activos
    - Depósitos
    - Patrimonio Neto
    - Préstamos

    Consolidado por banco con % sobre total.
    """

    print(f"\n🏦 BCRA request — top_n={top_n}")

    resultado = get_bcra_bancos(top_n=top_n)

    if "error" in resultado:
        raise HTTPException(
            status_code=500,
            detail=resultado["error"]
        )

    return resultado