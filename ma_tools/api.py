"""
🚀 DEALDESK API v2
Motor financiero universal para M&A: comps, DCF, WACC, búsqueda por sector.

CORRER LOCAL:
    uvicorn api:app --reload --port 8000

ENDPOINTS:
    GET  /                    → health check
    POST /comps               → genera comps (JSON + Excel)
    GET  /comps/excel         → descarga Excel
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

from bcra_scraper import get_bcra_bancos
from comps_automatico import (
    get_financials, get_dcf_inputs, calcular_wacc,
    generar_excel, _generar_excel_buffer, UNIVERSE, DEAL_CONFIG
)
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
    version="2.3.0"
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
    # Campos opcionales — si se pasan, sobreescriben la interpretación de Claude
    empresa_override: str = ""
    sector_override: str = ""
    revenue_override: float = 0      # en la moneda/escala que el usuario elija
    moneda: str = "USD"              # USD, ARS, BRL, MXN, COP
    escala: str = "mm"               # mm (millones), k (miles), b (billones)
    rango_min_pct: float = 30        # % mínimo vs revenue target
    rango_max_pct: float = 300       # % máximo vs revenue target

class CompsResponse(BaseModel):
    empresa_target: str
    sector: str
    revenue_target: float
    n_empresas_universe: int
    n_empresas_filtradas: int
    archivo: str
    mensaje: str

class FinancialsRequest(BaseModel):
    ticker: str
    incluir_wacc: bool = True
    risk_free_rate: float = 4.5        # % — US 10Y Treasury
    equity_risk_premium: float = 5.5   # % — Damodaran ERP

class SectorRequest(BaseModel):
    sector: str
    top_n: int = 10
    metrica: str = "Revenue ($mm)"    # columna para rankear

class WACCRequest(BaseModel):
    ticker: str
    risk_free_rate: float = 4.5
    equity_risk_premium: float = 5.5
    beta_override: Optional[float] = None
    cost_of_debt_override: Optional[float] = None
    tax_rate_override: Optional[float] = None

class NaturalRequest(BaseModel):
    """Endpoint universal: el analista escribe lo que necesita en lenguaje natural."""
    mensaje: str
    analista: str = "Analista"

class PrecedentsRequest(BaseModel):
    sector: str                          # ej: "Health Insurance", "Technology"
    region: str = "Global"              # ej: "LATAM", "Argentina", "Global"
    años: int = 5                        # últimos N años
    min_ev_mm: Optional[float] = None   # filtro mínimo de EV en $mm
    max_ev_mm: Optional[float] = None   # filtro máximo de EV en $mm

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def interpretar_pedido(mensaje: str) -> dict:
    """Usa Claude para extraer empresa, sector y revenue del mensaje — con conocimiento real de empresas."""
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
        max_tokens=300,
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
        "status": "✅ DealDesk API v2 funcionando",
        "version": "2.0.0",
        "endpoints": {
            "POST /comps":              "Genera tabla de comps (JSON + Excel)",
            "GET  /comps/excel":        "Descarga Excel del último análisis",
            "POST /financials":         "DCF inputs + WACC de cualquier empresa",
            "POST /financials/wacc":    "Calcula WACC con parámetros custom",
            "POST /financials/sector":  "Resumen financiero de un sector",
            "POST /ask":                "Lenguaje natural → cualquier análisis",
            "GET  /bcra/bancos":        "Rankings sistema financiero argentino (BCRA)",
        }
    }


@app.post("/comps", response_model=CompsResponse)
def generar_comps(request: CompsRequest):
    """Recibe mensaje en lenguaje natural y genera análisis de comps."""
    print(f"\n📨 Comps request: {request.mensaje}")

    # Si vienen overrides del frontend, usarlos directamente
    if request.empresa_override and request.sector_override and request.revenue_override:
        empresa = request.empresa_override
        sector  = request.sector_override
        # Convertir a USD mm según moneda y escala
        revenue_raw = request.revenue_override
        # Escala
        escala_mult = {"mm": 1, "k": 0.001, "b": 1000}.get(request.escala, 1)
        # Moneda → USD (tipos aproximados)
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
    print(f"   Descargando {len(tickers)} empresas para {sector}...")

    resultados = []
    for ticker in tickers:
        data = get_financials(ticker)
        if data and data.get("Revenue ($mm)"):
            resultados.append(data)
        time.sleep(0.2)

    if not resultados:
        raise HTTPException(status_code=500, detail="No se pudieron obtener datos financieros.")

    df = pd.DataFrame(resultados)

    # Rango ajustable desde el request
    rango_min = request.rango_min_pct / 100
    rango_max = request.rango_max_pct / 100
    rev_min  = revenue * rango_min
    rev_max  = revenue * rango_max
    df_filt  = df[(df["Revenue ($mm)"] >= rev_min) & (df["Revenue ($mm)"] <= rev_max)]

    config_override = {
        "empresa_target": empresa,
        "sector":         sector,
        "revenue_target": revenue,
        "rango_min_pct":  rango_min,
        "rango_max_pct":  rango_max,
        "analista":       request.analista,
        "fecha":          datetime.now().strftime("%d/%m/%Y"),
    }
    DEAL_CONFIG.update(config_override)
    archivo = generar_excel(df)

    return CompsResponse(
        empresa_target=empresa,
        sector=sector,
        revenue_target=revenue,
        n_empresas_universe=len(df),
        n_empresas_filtradas=len(df_filt),
        archivo=archivo,
        mensaje=f"✅ Comps de {empresa} listos. {len(df_filt)} empresas comparables encontradas."
    )


@app.post("/comps/excel")
def descargar_excel_post(request: CompsRequest):
    """Genera comps y devuelve Excel en memoria — funciona en Railway."""
    print(f"\n📥 Excel request: {request.mensaje}")
    try:
        params = interpretar_pedido(request.mensaje)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No pude interpretar: {str(e)}")

    empresa = params.get("empresa_target", "Target")
    sector  = params.get("sector", "Health Insurance")
    revenue = float(params.get("revenue_target", 1000))
    tickers = UNIVERSE.get(sector, UNIVERSE["Health Insurance"])

    resultados = []
    for ticker in tickers:
        data = get_financials(ticker)
        if data and data.get("Revenue ($mm)"):
            resultados.append(data)
        time.sleep(0.2)

    if not resultados:
        raise HTTPException(status_code=500, detail="No se pudieron obtener datos.")

    df = pd.DataFrame(resultados)
    DEAL_CONFIG.update({
        "empresa_target": empresa, "sector": sector, "revenue_target": revenue,
        "rango_min_pct": 0.3, "rango_max_pct": 3.0,
        "analista": request.analista, "fecha": datetime.now().strftime("%d/%m/%Y"),
    })

    # Excel formateado en memoria usando generar_excel_buffer
    fecha_str = datetime.now().strftime("%Y%m%d")
    fname = f"Comps_{empresa.replace(' ', '_')}_{fecha_str}.xlsx"

    buffer = io.BytesIO()
    # Generar el workbook con formato completo y guardarlo en buffer
    _generar_excel_buffer(df, buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


@app.post("/financials")
def get_financials_endpoint(request: FinancialsRequest):
    """
    DCF inputs + WACC de cualquier empresa por ticker.
    
    Ejemplo: {"ticker": "AAPL", "incluir_wacc": true}
    """
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
    """
    Calcula WACC con parámetros custom (podés overridear beta, cost of debt, tax rate).
    
    Ejemplo: {"ticker": "MSFT", "risk_free_rate": 4.2, "beta_override": 1.1}
    """
    data = get_dcf_inputs(request.ticker.upper())

    if "error" in data:
        raise HTTPException(status_code=404, detail=f"No se encontraron datos para {request.ticker}")

    # Aplicar overrides
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
    """
    Resumen financiero de las top N empresas de un sector.
    Útil para benchmarking rápido de WACC, márgenes, múltiplos.
    
    Ejemplo: {"sector": "Technology", "top_n": 5}
    """
    tickers = UNIVERSE.get(request.sector)
    if not tickers:
        sectores = list(UNIVERSE.keys())
        raise HTTPException(status_code=400, detail=f"Sector no encontrado. Disponibles: {sectores}")

    print(f"\n🏭 Sector request: {request.sector} (top {request.top_n})")

    resultados = []
    for ticker in tickers[:request.top_n * 2]:  # buscar más para asegurar top_n con datos
        data = get_dcf_inputs(ticker)
        if "error" not in data and data.get("revenue_mm"):
            resultados.append(data)
        if len(resultados) >= request.top_n:
            break
        time.sleep(0.2)

    if not resultados:
        raise HTTPException(status_code=500, detail="No se pudieron obtener datos del sector.")

    # Calcular WACC para cada uno
    for r in resultados:
        r["wacc"] = calcular_wacc(r)

    # Stats del sector
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



@app.post("/precedents")
def get_precedents(request: PrecedentsRequest):
    """
    Precedent transactions por sector y región usando Claude.
    Devuelve deals históricos estructurados: target, acquirer, año, EV, múltiplos.

    Ejemplo: {"sector": "Health Insurance", "region": "LATAM", "años": 5}
    """
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
            messages=[{{"role": "user", "content": prompt}}]
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

@app.post("/ask")
def ask_natural(request: NaturalRequest):
    """
    Endpoint universal en lenguaje natural.
    El analista escribe lo que necesita y la API decide qué traer.
    
    Ejemplos:
    - "Dame el WACC de Apple"
    - "Quiero los DCF inputs de Microsoft"  
    - "Benchmark del sector Technology, top 5"
    - "Comps de Swiss Medical, health insurance, $1B revenue"
    """
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

    # Routing según tipo de pedido
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



@app.get("/bcra/bancos")
def bcra_bancos(top_n: int = None):
    """
    Rankings consolidados del sistema financiero argentino (BCRA).
    Trae activos, depósitos, patrimonio neto y préstamos de todos los bancos con % sobre el total.

    Ejemplo: GET /bcra/bancos?top_n=20
    """
    print(f"\n🏦 BCRA request — top_n={top_n}")
    resultado = get_bcra_bancos(top_n=top_n)
    if "error" in resultado:
        raise HTTPException(status_code=500, detail=resultado["error"])
    return resultado


@app.get("/app", response_class=HTMLResponse)
def serve_app():
    html = pathlib.Path("index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)
