from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from comps_automatico import get_dcf_inputs, calcular_wacc, UNIVERSE

router = APIRouter()

# ─────────────────────────────────────────────
# MODELOS
# ─────────────────────────────────────────────

class FinancialsRequest(BaseModel):
    ticker: str
    incluir_wacc: bool = True
    risk_free_rate: float = 4.5
    equity_risk_premium: float = 5.5


class SectorRequest(BaseModel):
    sector: str
    top_n: int = 10
    metrica: str = "Revenue ($mm)"


class WACCRequest(BaseModel):
    ticker: str
    risk_free_rate: float = 4.5
    equity_risk_premium: float = 5.5

    beta_override: Optional[float] = None
    cost_of_debt_override: Optional[float] = None
    tax_rate_override: Optional[float] = None


# ─────────────────────────────────────────────
# FINANCIALS
# ─────────────────────────────────────────────

@router.post("/financials")
def get_financials_endpoint(request: FinancialsRequest):
    """
    Devuelve inputs para DCF y WACC de cualquier empresa.
    """

    print(f"\n📊 Financials request: {request.ticker}")

    data = get_dcf_inputs(request.ticker.upper())

    if "error" in data:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron datos para {request.ticker}: {data['error']}"
        )

    result = {
        "financials": data
    }

    if request.incluir_wacc:

        wacc = calcular_wacc(
            data,
            risk_free_rate=request.risk_free_rate,
            equity_risk_premium=request.equity_risk_premium
        )

        result["wacc"] = wacc

    return result


# ─────────────────────────────────────────────
# WACC
# ─────────────────────────────────────────────

@router.post("/financials/wacc")
def calcular_wacc_endpoint(request: WACCRequest):

    data = get_dcf_inputs(request.ticker.upper())

    if "error" in data:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontraron datos para {request.ticker}"
        )

    if request.beta_override:
        data["beta"] = request.beta_override

    if request.cost_of_debt_override:
        data["cost_of_debt_pct"] = request.cost_of_debt_override

    if request.tax_rate_override:
        data["tax_rate_pct"] = request.tax_rate_override

    wacc = calcular_wacc(
        data,
        risk_free_rate=request.risk_free_rate,
        equity_risk_premium=request.equity_risk_premium
    )

    return {
        "ticker": request.ticker.upper(),
        "empresa": data.get("empresa"),
        "inputs_usados": {
            "beta": data.get("beta"),
            "cost_of_debt_pct": data.get("cost_of_debt_pct"),
            "tax_rate_pct": data.get("tax_rate_pct"),
            "equity_weight_pct": data.get("equity_weight_pct"),
            "debt_weight_pct": data.get("debt_weight_pct"),
        },
        "wacc": wacc
    }


# ─────────────────────────────────────────────
# SECTOR
# ─────────────────────────────────────────────

@router.post("/financials/sector")
def sector_financials(request: SectorRequest):

    tickers = UNIVERSE.get(request.sector)

    if not tickers:
        sectores = list(UNIVERSE.keys())

        raise HTTPException(
            status_code=400,
            detail=f"Sector no encontrado. Disponibles: {sectores}"
        )

    print(f"\n🏭 Sector request: {request.sector} (top {request.top_n})")

    resultados = []

    for ticker in tickers[:request.top_n * 2]:

        data = get_dcf_inputs(ticker)

        if "error" not in data and data.get("revenue_mm"):
            resultados.append(data)

        if len(resultados) >= request.top_n:
            break

        time.sleep(0.2)

    if not resultados:
        raise HTTPException(
            status_code=500,
            detail="No se pudieron obtener datos del sector."
        )

    for r in resultados:
        r["wacc"] = calcular_wacc(r)

    df = pd.DataFrame(resultados)

    numericas = [
        "ebitda_margin_pct",
        "net_margin_pct",
        "ev_ebitda",
        "ev_revenue",
        "pe",
        "beta",
        "net_debt_ebitda",
        "rev_growth_pct",
        "fcf_margin_pct"
    ]

    stats = {}

    for col in numericas:

        if col in df.columns:

            vals = df[col].dropna()

            if len(vals):

                stats[col] = {
                    "mediana": round(vals.median(), 2),
                    "promedio": round(vals.mean(), 2),
                    "min": round(vals.min(), 2),
                    "max": round(vals.max(), 2),
                }

    wacc_vals = [
        r["wacc"].get("wacc_pct")
        for r in resultados
        if r["wacc"].get("wacc_pct")
    ]

    if wacc_vals:

        stats["wacc_pct"] = {
            "mediana": round(pd.Series(wacc_vals).median(), 2),
            "promedio": round(pd.Series(wacc_vals).mean(), 2),
            "min": round(min(wacc_vals), 2),
            "max": round(max(wacc_vals), 2),
        }

    return {
        "sector": request.sector,
        "n_empresas": len(resultados),
        "empresas": resultados,
        "stats_sector": stats,
    }