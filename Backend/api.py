"""
🚀 DEALDESK API v3
Motor financiero universal para M&A: comps, DCF, WACC, búsqueda por sector.

CORRER LOCAL:
    uvicorn api:app --reload --port 8000

ENDPOINTS:
    GET  /                    → health check
    GET  /api/empresas        → catálogo de empresas para autocomplete
    POST /comps               → genera comps (JSON + Excel)
    POST /comps/excel         → descarga Excel
    POST /financials          → datos DCF + WACC de cualquier empresa
    POST /financials/wacc     → calcula WACC con parámetros custom
    POST /financials/sector   → resumen financiero de un sector completo
    POST /precedents          → precedent transactions por sector/región
    POST /ask                 → lenguaje natural → cualquier análisis
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import pathlib
from pydantic import BaseModel
from typing import Optional
import anthropic
import json
import os
import sys
sys.path.append(os.path.dirname(__file__))
from scrapers.bcra_scraper import get_bcra_bancos
from Backend.comps_automatico import (
    get_financials, get_dcf_inputs, calcular_wacc,
    generar_excel, _generar_excel_buffer, UNIVERSE, DEAL_CONFIG
)
from financial_engine import get_financials_ttm, calculate_comps_stats, build_comps_response

import pandas as pd
import time
from datetime import datetime
import io
from fastapi.responses import StreamingResponse

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

app = FastAPI(
    title="DealDesk — M&A Financial API",
    description="Motor financiero universal: comps, DCF, WACC, búsqueda por sector.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# MODELOS
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

class NaturalRequest(BaseModel):
    mensaje: str
    analista: str = "Analista"

class PrecedentsRequest(BaseModel):
    sector: str
    region: str = "Global"
    años: int = 5
    min_ev_mm: Optional[float] = None
    max_ev_mm: Optional[float] = None

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def interpretar_pedido(mensaje: str) -> dict:
    """Usa Claude para extraer empresa, sector y revenue del mensaje."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Sos un analista senior de M&A. Extraé los datos del mensaje y devolvé SOLO JSON válido.

Mensaje: "{mensaje}"

IMPORTANTE: Si reconocés la empresa, usá su revenue real aproximado y su sector correcto:
- Mercado Libre / MELI → sector: Technology, revenue: 20000
- Apple / AAPL → sector: Technology, revenue: 400000
- Microsoft / MSFT → sector: Technology, revenue: 230000  
- Google / GOOGL → sector: Technology, revenue: 300000
- Amazon / AMZN → sector: Technology, revenue: 600000
- JPMorgan / JPM → sector: Financials, revenue: 160000
- UnitedHealth / UNH → sector: Health Insurance, revenue: 370000
- ExxonMobil / XOM → sector: Energy, revenue: 400000
- Walmart / WMT → sector: Consumer, revenue: 650000
- Si no conocés la empresa, usá el revenue del mensaje o 1000 como default.

Devolvé exactamente:
{{
  "empresa_target": "nombre de la empresa",
  "ticker": "ticker si lo conocés o null",
  "sector": "uno de: Health Insurance, Technology, Financials, Energy, Consumer, Real Estate, Industrials",
  "revenue_target": número en millones USD (solo el número)
}}

Solo el JSON, nada más."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def interpretar_financials(mensaje: str) -> dict:
    """Extrae ticker y tipo de análisis del mensaje en lenguaje natural."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Sos un analista de M&A. Extraé los datos del mensaje y devolvé SOLO JSON válido:

Mensaje: "{mensaje}"

Devolvé:
{{
  "ticker": "símbolo bursátil (ej: AAPL, MSFT, UNH)",
  "tipo": "uno de: dcf, wacc, comps, sector, todo",
  "sector": "si aplica: Health Insurance, Technology, Financials, Energy, Consumer, Real Estate, Industrials",
  "risk_free_rate": número o null,
  "equity_risk_premium": número o null
}}

Solo el JSON, nada más."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
def health_check():
    return {
        "status": "✅ DealDesk API v3 funcionando",
        "version": "3.0.0",
        "endpoints": {
            "GET  /api/empresas":       "Catálogo de empresas para autocomplete",
            "POST /comps":              "Genera tabla de comps con TTM real (JSON + Excel)",
            "POST /comps/excel":        "Descarga Excel del análisis",
            "POST /financials":         "DCF inputs + WACC de cualquier empresa",
            "POST /financials/wacc":    "Calcula WACC con parámetros custom",
            "POST /financials/sector":  "Resumen financiero de un sector",
            "POST /precedents":         "Precedent transactions por sector/región",
            "POST /ask":                "Lenguaje natural → cualquier análisis",
            "GET  /bcra/bancos":        "Rankings sistema financiero argentino (BCRA)",
        }
    }


# ─────────────────────────────────────────────
# AUTOCOMPLETE — catálogo de empresas
# ─────────────────────────────────────────────

@app.get("/api/empresas")
def get_empresas():
    """
    Devuelve el catálogo de empresas para autocomplete del frontend.
    Busca empresas.json en varias rutas posibles (local, Railway, etc).
    Si no encuentra el JSON, genera un catálogo desde UNIVERSE.
    """
    # Intentar varias rutas donde puede estar el JSON
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

    # Fallback: generar catálogo desde UNIVERSE (350 tickers aprox)
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


# ─────────────────────────────────────────────
# COMPS — con TTM real y stats pre-calculadas
# ─────────────────────────────────────────────

@app.post("/comps")
def generar_comps(request: CompsRequest):
    """
    Genera análisis de comps con TTM REAL.
    Revenue y EBITDA calculados desde quarterly financials (4Q sum).
    Múltiplos, stats (mean/median) y TTM quality incluidos en JSON.
    """
    print(f"\n📨 Comps request: {request.mensaje}")

    # ── Determinar parámetros del deal ──
    if request.empresa_override and request.sector_override and request.revenue_override:
        empresa = request.empresa_override
        sector  = request.sector_override
        revenue_raw = request.revenue_override
        escala_mult = {"mm": 1, "k": 0.001, "b": 1000}.get(request.escala, 1)
        fx = {"USD": 1, "ARS": 1/1200, "BRL": 1/5, "MXN": 1/17, "COP": 1/4000}
        fx_mult = fx.get(request.moneda, 1)
        revenue = revenue_raw * escala_mult * fx_mult
        print(f"   Override: {empresa} / {sector} / ${revenue:.0f}mm USD")
    else:
        try:
            params = interpretar_pedido(request.mensaje)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No pude interpretar el pedido: {str(e)}")
        empresa = params.get("empresa_target", "Target")
        sector  = params.get("sector", "Health Insurance")
        revenue = float(params.get("revenue_target", 1000))

    tickers = UNIVERSE.get(sector, UNIVERSE["Health Insurance"])
    print(f"   Descargando {len(tickers)} empresas con TTM real...")

    # ── Fetch con TTM real ──
    resultados = []
    for ticker in tickers:
        data = get_financials_ttm(ticker)
        if data and data.get("Revenue ($mm)"):
            resultados.append(data)
        time.sleep(0.15)

    if not resultados:
        raise HTTPException(status_code=500, detail="No se pudieron obtener datos financieros.")

    # ── Build response con stats pre-calculadas ──
    rango_min = request.rango_min_pct / 100
    rango_max = request.rango_max_pct / 100

    response = build_comps_response(
        empresas=resultados,
        empresa_target=empresa,
        sector=sector,
        revenue_target=revenue,
        rango_min_pct=rango_min,
        rango_max_pct=rango_max,
    )

    # ── También preparar Excel ──
    df = pd.DataFrame(resultados)
    DEAL_CONFIG.update({
        "empresa_target": empresa,
        "sector":         sector,
        "revenue_target": revenue,
        "rango_min_pct":  rango_min,
        "rango_max_pct":  rango_max,
        "analista":       request.analista,
        "fecha":          datetime.now().strftime("%d/%m/%Y"),
    })

    try:
        archivo = generar_excel(df)
        response["archivo"] = archivo
    except Exception as e:
        print(f"   ⚠️ Excel generation failed: {e}")
        response["archivo"] = None

    response["mensaje"] = (
        f"✅ Comps de {empresa} listos. "
        f"{response['n_empresas_filtradas']} empresas filtradas de {response['n_empresas_universe']}. "
        f"TTM real: {response['ttm_quality']['pct_real_ttm']}%"
    )

    return response


@app.post("/comps/excel")
def descargar_excel_post(request: CompsRequest):
    """Genera comps con TTM y devuelve Excel en memoria — funciona en Railway."""
    print(f"\n📥 Excel request: {request.mensaje}")

    # ── Parámetros ──
    if request.empresa_override and request.sector_override and request.revenue_override:
        empresa = request.empresa_override
        sector  = request.sector_override
        revenue_raw = request.revenue_override
        escala_mult = {"mm": 1, "k": 0.001, "b": 1000}.get(request.escala, 1)
        fx = {"USD": 1, "ARS": 1/1200, "BRL": 1/5, "MXN": 1/17, "COP": 1/4000}
        fx_mult = fx.get(request.moneda, 1)
        revenue = revenue_raw * escala_mult * fx_mult
    else:
        try:
            params = interpretar_pedido(request.mensaje)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"No pude interpretar: {str(e)}")
        empresa = params.get("empresa_target", "Target")
        sector  = params.get("sector", "Health Insurance")
        revenue = float(params.get("revenue_target", 1000))

    tickers = UNIVERSE.get(sector, UNIVERSE["Health Insurance"])

    # ── Fetch TTM ──
    resultados = []
    for ticker in tickers:
        data = get_financials_ttm(ticker)
        if data and data.get("Revenue ($mm)"):
            resultados.append(data)
        time.sleep(0.15)

    if not resultados:
        raise HTTPException(status_code=500, detail="No se pudieron obtener datos.")

    df = pd.DataFrame(resultados)
    DEAL_CONFIG.update({
        "empresa_target": empresa,
        "sector": sector,
        "revenue_target": revenue,
        "rango_min_pct": (request.rango_min_pct / 100) if request.rango_min_pct else 0.3,
        "rango_max_pct": (request.rango_max_pct / 100) if request.rango_max_pct else 3.0,
        "analista": request.analista,
        "fecha": datetime.now().strftime("%d/%m/%Y"),
    })

    fecha_str = datetime.now().strftime("%Y%m%d")
    fname = f"Comps_{empresa.replace(' ', '_')}_{fecha_str}.xlsx"

    buffer = io.BytesIO()
    _generar_excel_buffer(df, buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


# ─────────────────────────────────────────────
# FINANCIALS / DCF / WACC
# ─────────────────────────────────────────────

@app.post("/financials")
def get_financials_endpoint(request: FinancialsRequest):
    """DCF inputs + WACC de cualquier empresa por ticker."""
    print(f"\n📊 Financials request: {request.ticker}")

    data = get_dcf_inputs(request.ticker.upper())

    if "error" in data:
        raise HTTPException(status_code=404, detail=f"No se encontraron datos para {request.ticker}: {data['error']}")

    result = {"financials": data}

    if request.incluir_wacc:
        wacc = calcular_wacc(
            data,
            risk_free_rate=request.risk_free_rate,
            equity_risk_premium=request.equity_risk_premium
        )
        result["wacc"] = wacc

    return result


@app.post("/financials/wacc")
def calcular_wacc_endpoint(request: WACCRequest):
    """Calcula WACC con parámetros custom."""
    data = get_dcf_inputs(request.ticker.upper())

    if "error" in data:
        raise HTTPException(status_code=404, detail=f"No se encontraron datos para {request.ticker}")

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
        "ticker":         request.ticker.upper(),
        "empresa":        data.get("empresa"),
        "inputs_usados":  {
            "beta":               data.get("beta"),
            "cost_of_debt_pct":   data.get("cost_of_debt_pct"),
            "tax_rate_pct":       data.get("tax_rate_pct"),
            "equity_weight_pct":  data.get("equity_weight_pct"),
            "debt_weight_pct":    data.get("debt_weight_pct"),
        },
        "wacc": wacc
    }


@app.post("/financials/sector")
def sector_financials(request: SectorRequest):
    """Resumen financiero de las top N empresas de un sector."""
    tickers = UNIVERSE.get(request.sector)
    if not tickers:
        sectores = list(UNIVERSE.keys())
        raise HTTPException(status_code=400, detail=f"Sector no encontrado. Disponibles: {sectores}")

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
        raise HTTPException(status_code=500, detail="No se pudieron obtener datos del sector.")

    for r in resultados:
        r["wacc"] = calcular_wacc(r)

    df = pd.DataFrame(resultados)
    numericas = ["ebitda_margin_pct", "net_margin_pct", "ev_ebitda", "ev_revenue", "pe",
                 "beta", "net_debt_ebitda", "rev_growth_pct", "fcf_margin_pct"]

    stats = {}
    for col in numericas:
        if col in df.columns:
            vals = df[col].dropna()
            if len(vals):
                stats[col] = {
                    "mediana":  round(vals.median(), 2),
                    "promedio": round(vals.mean(), 2),
                    "min":      round(vals.min(), 2),
                    "max":      round(vals.max(), 2),
                }

    wacc_vals = [r["wacc"].get("wacc_pct") for r in resultados if r["wacc"].get("wacc_pct")]
    if wacc_vals:
        stats["wacc_pct"] = {
            "mediana":  round(pd.Series(wacc_vals).median(), 2),
            "promedio": round(pd.Series(wacc_vals).mean(), 2),
            "min":      round(min(wacc_vals), 2),
            "max":      round(max(wacc_vals), 2),
        }

    return {
        "sector":    request.sector,
        "n_empresas": len(resultados),
        "empresas":  resultados,
        "stats_sector": stats,
    }


# ─────────────────────────────────────────────
# PRECEDENTS
# ─────────────────────────────────────────────

@app.post("/precedents")
def get_precedents(request: PrecedentsRequest):
    """Precedent transactions por sector y región usando Claude."""
    print(f"\n📋 Precedents: {request.sector} / {request.region}")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    filtro_ev = ""
    if request.min_ev_mm and request.max_ev_mm:
        filtro_ev = f"Solo deals con EV entre ${request.min_ev_mm}mm y ${request.max_ev_mm}mm."
    elif request.min_ev_mm:
        filtro_ev = f"Solo deals con EV mayor a ${request.min_ev_mm}mm."
    elif request.max_ev_mm:
        filtro_ev = f"Solo deals con EV menor a ${request.max_ev_mm}mm."

    año_desde = datetime.now().year - request.años

    prompt = f"""Sos un analista senior de M&A. Lista precedent transactions del sector "{request.sector}" en "{request.region}" desde {año_desde}.

{filtro_ev}

Devolvé SOLO JSON valido:
{{
  "sector": "{request.sector}",
  "region": "{request.region}",
  "periodo": "{año_desde}-{datetime.now().year}",
  "fuente": "Deals publicamente reportados (prensa financiera, SEC, comunicados)",
  "deals": [
    {{
      "año": 2023,
      "target": "empresa adquirida",
      "acquirer": "comprador",
      "pais_target": "pais",
      "ev_mm": numero o null,
      "revenue_mm": numero o null,
      "ev_revenue": numero o null,
      "ev_ebitda": numero o null,
      "stake_pct": numero o null,
      "tipo": "Adquisicion total / Parcial / Fusion / LBO",
      "notas": "contexto en 1 linea"
    }}
  ],
  "estadisticas": {{
    "n_deals": numero,
    "ev_mediana_mm": numero o null,
    "ev_revenue_mediana": numero o null,
    "ev_ebitda_mediana": numero o null
  }},
  "advertencia": "Datos de fuentes publicas. Verificar antes de usar en un proceso."
}}

Incluí 5-15 deals reales. Solo el JSON, nada mas."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)

        if request.min_ev_mm or request.max_ev_mm:
            filtrados = []
            for deal in result.get("deals", []):
                ev = deal.get("ev_mm")
                if ev is None:
                    filtrados.append(deal)
                    continue
                if request.min_ev_mm and ev < request.min_ev_mm:
                    continue
                if request.max_ev_mm and ev > request.max_ev_mm:
                    continue
                filtrados.append(deal)
            result["deals"] = filtrados
            result["estadisticas"]["n_deals"] = len(filtrados)

        return result

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Error parseando respuesta: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ─────────────────────────────────────────────
# NATURAL LANGUAGE
# ─────────────────────────────────────────────

@app.post("/ask")
def ask_natural(request: NaturalRequest):
    """Endpoint universal en lenguaje natural."""
    print(f"\n🤖 Natural request: {request.mensaje}")

    try:
        params = interpretar_financials(request.mensaje)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No pude interpretar: {str(e)}")

    tipo   = params.get("tipo", "todo")
    ticker = params.get("ticker")
    sector = params.get("sector")
    rfr    = params.get("risk_free_rate") or 4.5
    erp    = params.get("equity_risk_premium") or 5.5

    if tipo == "sector" or (not ticker and sector):
        sec = sector or "Technology"
        return sector_financials(SectorRequest(sector=sec, top_n=5))

    if tipo == "comps":
        return generar_comps(CompsRequest(mensaje=request.mensaje, analista=request.analista))

    if ticker:
        data = get_dcf_inputs(ticker.upper())
        if "error" in data:
            raise HTTPException(status_code=404, detail=f"No se encontraron datos para {ticker}")

        wacc = calcular_wacc(data, risk_free_rate=rfr, equity_risk_premium=erp)

        return {
            "interpretado": params,
            "financials":   data,
            "wacc":         wacc,
        }

    raise HTTPException(status_code=400, detail="No pude identificar empresa ni sector en el mensaje.")


# ─────────────────────────────────────────────
# YAHOO FINANCE PROXY (fallback)
# ─────────────────────────────────────────────

@app.get("/yf/search")
async def yf_search(q: str):
    import httpx

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=8&newsCount=0&listsCount=0"

    async with httpx.AsyncClient() as client:
        res = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

    return res.json()

@app.get("/yf/{ticker}")
async def yf_quote(ticker: str):
    import httpx

    async with httpx.AsyncClient() as client:

        chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
        chart_res = await client.get(
            chart_url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        chart = chart_res.json()
        result = chart.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})

        quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        quote_res = await client.get(
            quote_url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        quote = quote_res.json()
        q = quote.get("quoteResponse", {}).get("result", [{}])[0]

        return {
            "ticker": ticker,
            "price": meta.get("regularMarketPrice"),
            "marketCap": q.get("marketCap"),
            "enterpriseValue": q.get("enterpriseValue"),
            "revenue": q.get("totalRevenue"),
            "ebitda": q.get("ebitda"),
            "netIncome": q.get("netIncomeToCommon"),
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "sector": q.get("sector"),
            "industry": q.get("industry")
        }


# ─────────────────────────────────────────────
# BCRA
# ─────────────────────────────────────────────

@app.get("/bcra/bancos")
def bcra_bancos(top_n: int = None):
    """Rankings del sistema financiero argentino (BCRA)."""
    print(f"\n🏦 BCRA request — top_n={top_n}")
    resultado = get_bcra_bancos(top_n=top_n)
    if "error" in resultado:
        raise HTTPException(status_code=500, detail=resultado["error"])
    return resultado


@app.get("/app", response_class=HTMLResponse)
def serve_app():
    html = pathlib.Path("index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)