from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pathlib
import json
import os
import sys
import pandas as pd
import time
from datetime import datetime
import io
from fastapi.responses import StreamingResponse
import traceback

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from Backend.financial_engine import (
    get_financials_ttm,
    build_comps_response
)

from Backend.comps_automatico import (
    generar_excel,
    _generar_excel_buffer,
    DEAL_CONFIG
)
router = APIRouter()

# ─────────────────────────────────────────────
# MODELO
# ─────────────────────────────────────────────

class CompsRequest(BaseModel):

    mensaje: str

    analista: str = "Analista"

    empresa_override: str = ""
    sector_override: str = ""
    revenue_override: float = 0

    moneda: str = "USD"
    escala: str = "mm"

    rango_min_pct: float = 30
    rango_max_pct: float = 300


# ─────────────────────────────────────────────
# CARGAR EMPRESAS.JSON
# ─────────────────────────────────────────────

def load_empresas():

    base = pathlib.Path(__file__).resolve().parents[2]

    posibles_rutas = [
        base / "FrontEnd" / "Data" / "empresas.json",
        base / "Data" / "empresas.json",
        base / "empresas.json"
    ]

    for path in posibles_rutas:

        try:

            if path.exists():

                data = json.loads(path.read_text(encoding="utf-8"))

                print(f"✅ empresas.json cargado ({len(data)} empresas)")

                return data

        except Exception:
            continue

    print("⚠️ empresas.json no encontrado")

    return []
# ─────────────────────────────────────────────
# UNIVERSO POR SECTOR
# ─────────────────────────────────────────────

def get_universe_by_sector(sector: str):

    empresas = load_empresas()

    tickers = [

        e["ticker"]

        for e in empresas

        if e.get("sector", "").lower() == sector.lower()

    ]

    return tickers


# ─────────────────────────────────────────────
# COMPS
# ─────────────────────────────────────────────
"""
🚀 DEALDESK API v3

Backend principal del motor financiero DealDesk.

Arquitectura modular:
    modules/
        bcra.py
        comps.py
        empresas.py
        financials.py
        precedents.py
        ask_ai.py

Run local:
    uvicorn Backend.api:app --reload --port 8000
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import pathlib
import httpx

# ─────────────────────────────────────────────
# IMPORTAR ROUTERS
# ─────────────────────────────────────────────

from Backend.modules.bcra import router as bcra_router
from Backend.modules.comps import router as comps_router
from Backend.modules.empresas import router as empresas_router
from Backend.modules.financials import router as financials_router
from Backend.modules.precedents import router as precedents_router

# opcional si usás ask_ai
try:
    from Backend.modules.ask_ai import router as ask_router
    HAS_ASK = True
except Exception:
    HAS_ASK = False


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="DealDesk — M&A Financial API",
    description="Motor financiero universal",
    version="3.0.0"
)


# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # permite cualquier frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# PRE-FLIGHT HANDLER (OPTIONS)
# ─────────────────────────────────────────────

@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )
# ─────────────────────────────────────────────
# REGISTRAR ROUTERS
# ─────────────────────────────────────────────

app.include_router(empresas_router)
app.include_router(comps_router)
app.include_router(financials_router)
app.include_router(precedents_router)
app.include_router(bcra_router)

if HAS_ASK:
    app.include_router(ask_router)


# ─────────────────────────────────────────────
# YAHOO SEARCH PROXY
# ─────────────────────────────────────────────

@app.get("/yf/search")
async def yf_search(q: str):

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=8&newsCount=0"

    async with httpx.AsyncClient() as client:
        res = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

    return res.json()


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.get("/")
def health_check():

    return {
        "status": "✅ DealDesk API funcionando",
        "version": "3.0.0",
        "endpoints": {

            "GET  /api/empresas": "Catálogo de empresas",
            "GET  /yf/search": "Buscar empresas (Yahoo proxy)",

            "POST /comps": "Comparable Companies",
            "POST /comps/excel": "Descargar Excel",

            "POST /financials": "Financial data",
            "POST /financials/wacc": "Calcular WACC",
            "POST /financials/sector": "Sector analysis",

            "POST /precedents": "Precedent transactions",

            "GET /bcra/bancos": "Sistema financiero argentino"
        }
    }


# ─────────────────────────────────────────────
# SERVIR FRONTEND
# ─────────────────────────────────────────────

@app.get("/app", response_class=HTMLResponse)
def serve_app():

    html = pathlib.Path("index.html").read_text(encoding="utf-8")

    return HTMLResponse(content=html)

# ─────────────────────────────────────────────
# EXCEL DOWNLOAD
# ─────────────────────────────────────────────
@router.post("/comps")
def generar_comps(request: CompsRequest):

    try:

        empresa = request.empresa_override
        sector = request.sector_override
        revenue = request.revenue_override

        tickers = get_universe_by_sector(sector)[:50]

        empresas = []

        for ticker in tickers:

            data = get_financials_ttm(ticker)

            if not data:
                continue

            empresas.append(data)

        if not empresas:

            raise HTTPException(
                status_code=500,
                detail="No se pudieron obtener empresas"
            )

        result = build_comps_response(
            empresas,
            empresa,
            sector,
            revenue,
            request.rango_min_pct / 100,
            request.rango_max_pct / 100
        )

        return result

    except Exception as e:

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
@router.post("/comps/excel")
def descargar_excel(request: CompsRequest):

    empresa = request.empresa_override
    sector = request.sector_override
    revenue = request.revenue_override

    tickers = get_universe_by_sector(sector)[:25]

    resultados = []

    for ticker in tickers:

        data = get_financials_ttm(ticker)

        if not data:
            continue

        if data.get("Revenue ($mm)") is None:
            continue

        resultados.append(data)

    if not resultados:

        raise HTTPException(
            status_code=500,
            detail="No se pudieron obtener datos"
        )

    df = pd.DataFrame(resultados)

    DEAL_CONFIG.update({

        "empresa_target": empresa,
        "sector": sector,
        "revenue_target": revenue,
        "rango_min_pct": request.rango_min_pct / 100,
        "rango_max_pct": request.rango_max_pct / 100,
        "analista": request.analista,
        "fecha": datetime.now().strftime("%d/%m/%Y"),

    })

    fecha_str = datetime.now().strftime("%Y%m%d")

    fname = f"Comps_{empresa.replace(' ','_')}_{fecha_str}.xlsx"

    buffer = io.BytesIO()

    _generar_excel_buffer(df, buffer)

    buffer.seek(0)

    return StreamingResponse(

        buffer,

        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

        headers={

            "Content-Disposition": f'attachment; filename="{fname}"'

        }

    )