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

Correr local:
    uvicorn api:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import pathlib


# ─────────────────────────────────────────────
# IMPORTAR ROUTERS
# ─────────────────────────────────────────────

from modules.bcra import router as bcra_router
from modules.comps import router as comps_router
from modules.empresas import router as empresas_router
from modules.financials import router as financials_router
from modules.precedents import router as precedents_router


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="DealDesk — M&A Financial API",
    description="Motor financiero universal: comps, DCF, WACC, precedents, BCRA.",
    version="3.0.0"
)


# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://web-production-f0fe2.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# REGISTRAR ROUTERS
# ─────────────────────────────────────────────

app.include_router(empresas_router)
app.include_router(comps_router)
app.include_router(financials_router)
app.include_router(precedents_router)
app.include_router(bcra_router)


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.get("/")
def health_check():

    return {
        "status": "✅ DealDesk API funcionando",
        "version": "3.0.0",
        "endpoints": {

            "GET  /api/empresas":       "Catálogo de empresas para autocomplete",

            "POST /comps":              "Comparable Companies",
            "POST /comps/excel":        "Descargar Excel de comps",

            "POST /financials":         "DCF inputs + WACC",
            "POST /financials/wacc":    "Calcular WACC custom",
            "POST /financials/sector":  "Análisis sectorial",

            "POST /precedents":         "Precedent transactions",

            "POST /ask":                "Lenguaje natural → análisis",

            "GET  /bcra/bancos":        "Rankings sistema financiero argentino"
        }
    }


# ─────────────────────────────────────────────
# SERVIR FRONTEND
# ─────────────────────────────────────────────

@app.get("/app", response_class=HTMLResponse)
def serve_app():

    html = pathlib.Path("index.html").read_text(encoding="utf-8")

    return HTMLResponse(content=html)