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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import pathlib
import httpx
import io
import pandas as pd
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from Backend.comps_automatico import (
    get_universe_by_sector,
    get_financials,
    _generar_excel_buffer,
)
from fastapi import Request, Response

# ─────────────────────────────────────────────
# IMPORTAR ROUTERS
# ─────────────────────────────────────────────

from Backend.modules.bcra import router as bcra_router
from Backend.modules.comps import router as comps_router
from Backend.modules.empresas import router as empresas_router
from Backend.modules.financials import router as financials_router
from Backend.modules.precedents import router as precedents_router
from Backend.modules.bcra_export import router as bcra_export_router
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    return Response(status_code=200)
from fastapi import Request
from fastapi.responses import Response

@app.options("/comps")
async def options_comps(request: Request):
    return Response(status_code=200)
# ─────────────────────────────────────────────
# REGISTRAR ROUTERS
# ─────────────────────────────────────────────

app.include_router(empresas_router)
app.include_router(comps_router)
app.include_router(financials_router)
app.include_router(precedents_router)
app.include_router(bcra_router)
app.include_router(bcra_export_router)
if HAS_ASK:
    app.include_router(ask_router)
app.mount("/", StaticFiles(directory="FrontEnd", html=True), name="frontend")


# ─────────────────────────────────────────────
# YAHOO SEARCH PROXY
# (usado por el buscador de empresas)
# ─────────────────────────────────────────────
import httpx

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

@app.get("/api")
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

