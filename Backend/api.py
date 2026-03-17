"""
🚀 DEALDESK API v3

Backend principal del motor financiero DealDesk.
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import httpx

# ─────────────────────────────────────────────
# IMPORTAR ROUTERS
# ─────────────────────────────────────────────

from Backend.modules.bcra import router as bcra_router
from Backend.modules.comps import router as comps_router
from Backend.modules.empresas import router as empresas_router
from Backend.modules.financials import router as financials_router
from Backend.modules.precedents import router as precedents_router
from Backend.modules.bcra_export import router as bcra_export_router

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# OPTIONS (CORS)
# ─────────────────────────────────────────────

@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    return Response(status_code=200)


@app.options("/comps")
async def options_comps(request: Request):
    return Response(status_code=200)


# ─────────────────────────────────────────────
# REGISTRAR ROUTERS API
# ─────────────────────────────────────────────

app.include_router(empresas_router)
app.include_router(comps_router)
app.include_router(financials_router)
app.include_router(precedents_router)
app.include_router(bcra_router)
app.include_router(bcra_export_router)

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

@app.get("/api")
def health_check():
    return {
        "status": "✅ DealDesk API funcionando",
        "version": "3.0.0"
    }


# ─────────────────────────────────────────────
# SERVIR FRONTEND
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse("FrontEnd/Html/index.html")


# ESTÁTICOS (AL FINAL)
app.mount("/css", StaticFiles(directory="FrontEnd/css"), name="css")
app.mount("/js", StaticFiles(directory="FrontEnd/js"), name="js")
app.mount("/components", StaticFiles(directory="FrontEnd/Html/Components"), name="components")
app.mount("/data", StaticFiles(directory="FrontEnd/Data"), name="data")