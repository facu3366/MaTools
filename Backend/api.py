from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import pathlib

from Backend.modules.bcra import router as bcra_router
from Backend.modules.comps import router as comps_router
from Backend.modules.empresas import router as empresas_router
from Backend.modules.financials import router as financials_router
from Backend.modules.precedents import router as precedents_router

app = FastAPI(
    title="DealDesk — M&A Financial API",
    description="Motor financiero universal: comps, DCF, WACC, precedents, BCRA.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(empresas_router)
app.include_router(comps_router)
app.include_router(financials_router)
app.include_router(precedents_router)
app.include_router(bcra_router)

@app.get("/")
def health_check():
    return {
        "status": "✅ DealDesk API funcionando",
        "version": "3.0.0"
    }

@app.get("/app", response_class=HTMLResponse)
def serve_app():
    html = pathlib.Path("index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)