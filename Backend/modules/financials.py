from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import pathlib
import json
import pandas as pd
import time

from Backend.comps_automatico import get_dcf_inputs, calcular_wacc

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


class WACCRequest(BaseModel):

    ticker: str

    risk_free_rate: float = 4.5
    equity_risk_premium: float = 5.5

    beta_override: Optional[float] = None
    cost_of_debt_override: Optional[float] = None
    tax_rate_override: Optional[float] = None


# ─────────────────────────────────────────────
# CARGAR EMPRESAS.JSON
# ─────────────────────────────────────────────

def load_empresas():

    posibles_rutas = [

        "FrontEnd/Data/empresas.json",
        "../FrontEnd/Data/empresas.json",
        "Data/empresas.json",
        "empresas.json"

    ]

    for ruta in posibles_rutas:

        path = pathlib.Path(ruta)

        if path.exists():

            try:

                data = json.loads(path.read_text(encoding="utf-8"))

                print(f"✅ empresas.json cargado ({len(data)} empresas)")

                return data

            except Exception:

                continue

    return []


# ─────────────────────────────────────────────
# UNIVERSO POR SECTOR
# ─────────────────────────────────────────────

def get_universe_by_sector(sector):

    empresas = load_empresas()

    tickers = [

        e["ticker"]

        for e in empresas

        if e.get("sector") == sector

    ]

    return tickers


# ─────────────────────────────────────────────
# FINANCIALS POR EMPRESA
# ─────────────────────────────────────────────

@router.post("/financials")
def get_financials_endpoint(request: FinancialsRequest):

    print(f"\n📊 Financials request: {request.ticker}")

    data = get_dcf_inputs(request.ticker.upper())

    if "error" in data:

        raise HTTPException(

            status_code=404,
            detail=f"No se encontraron datos para {request.ticker}"

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
# WACC CUSTOM
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
# SECTOR ANALYSIS
# ─────────────────────────────────────────────

def sector_financials(request: SectorRequest):

    tickers = get_universe_by_sector(request.sector)

    if not tickers:

        raise HTTPException(

            status_code=400,
            detail=f"No hay empresas cargadas para el sector {request.sector}"

        )

    print(f"\n🏭 Sector request: {request.sector}")

    resultados = []

    for ticker in tickers[: request.top_n * 2]:

        data = get_dcf_inputs(ticker)

        if "error" not in data and data.get("revenue_mm"):

            resultados.append(data)

        if len(resultados) >= request.top_n:

            break

        time.sleep(0.2)

    if not resultados:

        raise HTTPException(

            status_code=500,
            detail="No se pudieron obtener datos del sector"

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

    return {

        "sector": request.sector,
        "n_empresas": len(resultados),
        "empresas": resultados,
        "stats_sector": stats,

    }


@router.post("/financials/sector")
def sector_financials_endpoint(request: SectorRequest):

    return sector_financials(request)