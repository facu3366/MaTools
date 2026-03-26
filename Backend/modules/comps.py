"""
📊 COMPS MODULE v12 — AI-POWERED FILTERING (FIXED)
=============================================================
FIX in v12:
- INDUSTRY_PEERS always injected (removed < 5 gate that blocked auto peers)
- discover_comps sends ALL candidates to AI filter (no pre-filtering by static industry)
- AI filter is the ONLY intelligent filter — static filter removed to avoid conflicts
- Target industry detected via direct yfinance call (bypasses sanitize_empresa)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

import pathlib
import json
import pandas as pd
import io
import traceback
import math
from datetime import datetime
import yfinance as yf
import logging

from Backend.financial_engine import (
    get_financials_ttm,
    fetch_many_parallel,
    build_comps_response
)

from Backend.comps_automatico import (
    _generar_excel_buffer,
    DEAL_CONFIG
)

# ── AI Filter ──
try:
    from Backend.modules.ai_filter import ai_filter_comps_cached
    HAS_AI_FILTER = True
    print("✅ AI Comp Filter loaded")
except ImportError as e:
    HAS_AI_FILTER = False
    print(f"⚠️ AI Comp Filter not available: {e}")

router = APIRouter()
logger = logging.getLogger(__name__)


def clean_inf(obj):
    if isinstance(obj, dict):
        return {k: clean_inf(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_inf(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    return obj


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
    region: str = "GLOBAL"


# ─────────────────────────────────────────────
# EMPRESAS.JSON LOADER
# ─────────────────────────────────────────────

_empresas_cache = None

def load_empresas():
    global _empresas_cache
    if _empresas_cache is not None:
        return _empresas_cache
    base = pathlib.Path(__file__).resolve().parents[2]
    for path in [base / "FrontEnd" / "Data" / "empresas.json", base / "Data" / "empresas.json", base / "empresas.json"]:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                print(f"✅ empresas.json cargado ({len(data)} empresas)")
                _empresas_cache = data
                return data
        except Exception:
            continue
    _empresas_cache = []
    return []

def get_universe_by_sector(sector: str):
    return [e["ticker"] for e in load_empresas() if e.get("sector", "").lower() == sector.lower()]


# ─────────────────────────────────────────────
# YAHOO INDUSTRY PEERS
# ─────────────────────────────────────────────

def discover_industry_peers(industry_key: str) -> list[str]:
    if not industry_key:
        return []
    try:
        ind = yf.Industry(industry_key)
        tc = ind.top_companies
        if tc is not None and not tc.empty:
            tickers = list(tc.index)
            print(f"   🔍 Yahoo Industry '{industry_key}': {len(tickers)} peers → {tickers[:10]}...")
            return tickers
    except Exception as e:
        logger.warning(f"yf.Industry('{industry_key}') failed: {e}")
    return []


# ─────────────────────────────────────────────
# INDUSTRY_PEERS — ALWAYS INJECTED
# ─────────────────────────────────────────────

INDUSTRY_PEERS = {
    "Auto Manufacturers": [
        "TM", "GM", "F", "STLA", "HMC", "VWAGY", "BMWYY", "MBGAF",
        "RIVN", "LCID", "NIO", "XPEV", "LI", "BYDDY", "RACE", "TTM",
    ],
    "Auto Parts": [
        "APTV", "BWA", "LEA", "ALV", "MGA", "GNTX", "DAN", "VC", "AXL", "SMP",
    ],
    "Airlines": [
        "DAL", "UAL", "LUV", "AAL", "ALK", "JBLU", "RYAAY", "CPA", "GOL", "AZUL",
    ],
    "Restaurants": [
        "MCD", "SBUX", "YUM", "CMG", "DPZ", "QSR", "DRI", "TXRH", "WING", "SHAK", "WEN", "ARCO",
    ],
    "Residential Construction": [
        "DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MDC", "MHO", "TMHC", "GRBK",
    ],
    "Home Improvement Retail": ["HD", "LOW", "FND", "SHW", "WSM", "RH"],
    "Discount Stores": ["WMT", "TGT", "COST", "DG", "DLTR", "BJ", "OLLI", "FIVE"],
    "Grocery Stores": ["KR", "ACI", "SFM", "GO", "WMK"],
    "Utilities - Regulated Electric": [
        "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "WEC", "ES", "ED", "ETR", "PPL",
    ],
    "Entertainment": ["DIS", "CMCSA", "NFLX", "WBD", "PARA", "LYV", "AMC"],
    "Insurance - Property & Casualty": ["PGR", "ALL", "TRV", "CB", "HIG", "WRB", "ACGL", "MKL"],
    "Apparel Manufacturers": ["NKE", "ADDYY", "PVH", "RL", "HBI", "VFC", "LULU", "UAA", "SKX", "CROX"],
    "Recreational Vehicles": ["THO", "WGO", "CWH", "PII", "HOG", "MBUU"],
    "Drug Manufacturers - General": ["JNJ", "LLY", "PFE", "MRK", "ABBV", "BMY", "NVS", "AZN", "SNY", "GSK", "NVO"],
    "Biotechnology": ["AMGN", "GILD", "VRTX", "REGN", "BIIB", "MRNA", "ALNY", "BMRN", "INCY"],
    "Consumer Electronics": ["AAPL", "SONY", "SSNLF", "LOGI", "SONO", "GPRO"],
    "Footwear & Accessories": ["NKE", "ADDYY", "SKX", "CROX", "DECK", "ONON", "BIRK"],
    "Health Care Plans": ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"],
    "Internet Retail": ["AMZN", "BABA", "JD", "PDD", "MELI", "SE", "CPNG", "ETSY"],
    "Software - Application": ["CRM", "ADBE", "NOW", "INTU", "WDAY", "HUBS", "VEEV", "DDOG", "ZS", "CRWD"],
    "Software - Infrastructure": ["MSFT", "ORCL", "SNOW", "MDB", "NET", "DDOG", "ESTC", "CFLT"],
    "Semiconductors": ["NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU", "MRVL", "ADI", "NXPI"],
    "Banks - Diversified": ["JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "TFC"],
    "Banks - Regional": ["FITB", "RF", "CFG", "HBAN", "MTB", "ZION", "KEY", "CMA", "FHN"],
    "Oil & Gas Integrated": ["XOM", "CVX", "SHEL", "TTE", "BP", "COP", "EOG"],
    "Oil & Gas E&P": ["COP", "EOG", "PXD", "DVN", "FANG", "OXY", "HES", "MPC"],
}

INDUSTRY_KEY_ALTERNATIVES = {
    "auto-manufacturers": ["automobiles", "automobile-manufacturers", "automotive"],
    "airlines": ["passenger-airlines"],
    "utilities---regulated-electric": ["utilities-regulated-electric", "electric-utilities"],
    "insurance---property-and-casualty": ["insurance-property-and-casualty", "property-casualty-insurance"],
    "residential-construction": ["homebuilders", "home-builders"],
    "consumer-electronics": ["consumer-electronics", "electronics"],
}

INDUSTRY_TO_JSON_SECTORS = {
    "Internet Retail":          [("Consumer", 15), ("Technology", 10)],
    "Broadline Retail":         [("Consumer", 20)],
    "Software - Application":           [("Technology", 25)],
    "Software - Infrastructure":        [("Technology", 25)],
    "Information Technology Services":  [("Technology", 25)],
    "Internet Content & Information":   [("Technology", 20)],
    "Semiconductors":                       [("Technology", 20)],
    "Credit Services":                      [("Financials", 25)],
    "Capital Markets":                      [("Financials", 25)],
    "Banks - Diversified":                  [("Financials", 25)],
    "Banks - Regional":                     [("Financials", 25)],
    "Health Care Plans":                [("Health Insurance", 25)],
    "Drug Manufacturers - General":     [("Health Insurance", 25)],
    "Biotechnology":                    [("Health Insurance", 25)],
    "Oil & Gas Integrated":             [("Energy", 25)],
    "Oil & Gas E&P":                    [("Energy", 25)],
    "Aerospace & Defense":              [("Industrials", 25)],
    "Auto Manufacturers":               [("Consumer", 15), ("Industrials", 10)],
    "Restaurants":              [("Consumer", 20)],
    "Entertainment":            [("Consumer", 15), ("Technology", 10)],
}

MAX_JSON_TICKERS = 40
MAX_TOTAL_TICKERS = 80


# ─────────────────────────────────────────────
# REGION HELPERS
# ─────────────────────────────────────────────

def get_region_from_country(pais: str) -> str:
    if not pais:
        return "OTHER"
    if pais in ["Argentina", "Brazil", "Mexico", "Chile", "Colombia", "Peru", "Uruguay",
                "Paraguay", "Bolivia", "Ecuador", "Venezuela", "Costa Rica", "Panama",
                "Guatemala", "Dominican Republic", "El Salvador", "Honduras", "Nicaragua"]:
        return "LATAM"
    if pais in ["United States", "USA", "United States of America"]:
        return "US"
    if pais in ["Germany", "France", "Spain", "Italy", "Luxembourg", "Ireland",
                "Netherlands", "Switzerland", "Sweden", "Norway", "Denmark", "Finland",
                "Belgium", "Austria", "Portugal", "Poland", "Czech Republic", "Greece",
                "Hungary", "Romania", "Ukraine", "United Kingdom", "UK"]:
        return "EU"
    if pais in ["China", "Hong Kong", "Singapore", "India", "Japan", "Indonesia",
                "South Korea", "Taiwan", "Thailand", "Philippines", "Malaysia",
                "Vietnam", "Pakistan", "Bangladesh", "Saudi Arabia", "UAE", "Qatar", "Israel"]:
        return "ASIA"
    if pais in ["South Africa", "Egypt", "Nigeria", "Kenya", "Morocco", "Ghana",
                "Ethiopia", "Algeria", "Tunisia"]:
        return "AFRICA"
    if pais in ["Australia", "New Zealand"]:
        return "OCEANIA"
    return "OTHER"

COUNTRY_TO_REGION = {"Argentina": "LATAM", "Brazil": "LATAM", "Mexico": "LATAM"}


# ─────────────────────────────────────────────
# CLEAN & DEDUP
# ─────────────────────────────────────────────

def clean_and_dedup(empresas: list[dict], target_ticker: str = "", target_revenue: float = 0, rango_min_pct: float = 0.30, rango_max_pct: float = 3.0) -> list[dict]:
    target_upper = target_ticker.upper() if target_ticker else ""
    empresas = [e for e in empresas if e.get("Ticker", "").upper() != target_upper]

    clean = []
    for e in empresas:
        rev = e.get("Revenue ($mm)")
        ev = e.get("EV ($mm)")
        if not rev or rev <= 0:
            continue
        if not ev or ev <= 0:
            continue
        ebitda = e.get("EBITDA ($mm)")
        if ebitda is not None and ebitda < 0:
            continue
        ev_rev = ev / rev
        if ev_rev > 40:
            continue
        if ebitda is not None and ebitda > 0:
            ev_ebitda = ev / ebitda
            if ev_ebitda > 75:
                continue
        gross = e.get("Gross ($mm)")
        if gross and rev > 0:
            gm = gross / rev * 100
            if gm > 100:
                continue
        clean.append(e)

    if target_revenue and target_revenue > 0:
        min_rev = target_revenue * rango_min_pct
        max_rev = target_revenue * rango_max_pct
        before = len(clean)
        clean = [e for e in clean if min_rev <= e.get("Revenue ($mm)", 0) <= max_rev]
        filtered = before - len(clean)
        if filtered > 0:
            print(f"   📏 Revenue range ${min_rev:,.0f}-${max_rev:,.0f}mm: {filtered} fuera de rango")

    revenue_map = {}
    for e in clean:
        rev_key = round(e.get("Revenue ($mm)", 0), 0)
        ticker = e.get("Ticker", "")
        if rev_key not in revenue_map:
            revenue_map[rev_key] = e
        else:
            existing_ticker = revenue_map[rev_key].get("Ticker", "")
            if "." in existing_ticker and "." not in ticker:
                revenue_map[rev_key] = e
    
    result = list(revenue_map.values())
    result.sort(key=lambda e: e.get("Revenue ($mm)", 0), reverse=True)
    print(f"   🧹 Clean & dedup: {len(result)} comps (de {len(empresas)} candidatos)")
    result = clean_inf(result)
    return result


# ─────────────────────────────────────────────
# DISCOVER COMPS v12 — FIXED
# ─────────────────────────────────────────────

def discover_comps(target_ticker: str, target_industry: str, industry_key: str) -> list[dict]:
    all_tickers = set()

    # ── SOURCE A: Yahoo Finance Industry ──
    yahoo_tickers = discover_industry_peers(industry_key)
    all_tickers.update(yahoo_tickers)
    n_yahoo = len(yahoo_tickers)

    # ── SOURCE A2: Alternative industry keys ──
    if n_yahoo < 5 and industry_key:
        alt_keys = INDUSTRY_KEY_ALTERNATIVES.get(industry_key, [])
        for alt_key in alt_keys:
            alt_peers = discover_industry_peers(alt_key)
            if alt_peers:
                all_tickers.update(alt_peers)
                n_yahoo += len(alt_peers)
                print(f"   🔍 Source A2: alt key '{alt_key}' → {len(alt_peers)} peers")
                break

    # ── SOURCE D: Manual curated peers — ALWAYS ADDED (no gate) ──
    n_manual = 0
    if target_industry and target_industry in INDUSTRY_PEERS:
        manual = INDUSTRY_PEERS[target_industry]
        all_tickers.update(manual)
        n_manual = len(manual)
        print(f"   🔍 Source D: INDUSTRY_PEERS['{target_industry}'] → {n_manual} manual peers (ALWAYS)")

    # Also add similar industries' peers
    if target_industry:
        for key, peers in INDUSTRY_PEERS.items():
            if key != target_industry and target_industry.lower() in key.lower():
                all_tickers.update(peers)
                print(f"   🔍 Source D (partial match): '{key}' → {len(peers)} peers")

    # ── SOURCE C: yf.Sector() — adds broad candidates for AI to filter ──
    if target_ticker:
        try:
            t_info = yf.Ticker(target_ticker.upper()).info or {}
            sector_yf = t_info.get("sector", "")
            if sector_yf:
                sector_key = sector_yf.lower().replace(" ", "-").replace("&", "and")
                try:
                    sec = yf.Sector(sector_key)
                    tc = sec.top_companies
                    if tc is not None and not tc.empty:
                        sector_peers = list(tc.index)[:30]
                        print(f"   🔍 Source C: yf.Sector('{sector_key}'): {len(sector_peers)} peers")
                        all_tickers.update(sector_peers)
                except Exception as e:
                    print(f"   ⚠️ yf.Sector failed: {e}")
        except Exception as e:
            print(f"   ⚠️ Source C failed: {e}")

    # ── SOURCE B: empresas.json ──
    json_tickers = []
    if target_industry and target_industry in INDUSTRY_TO_JSON_SECTORS:
        sector_limits = INDUSTRY_TO_JSON_SECTORS[target_industry]
        for sector_name, max_from_sector in sector_limits:
            sector_tickers = get_universe_by_sector(sector_name)
            json_tickers.extend(sector_tickers[:max_from_sector])
    elif target_industry:
        all_empresas = load_empresas()
        target_data = next((e for e in all_empresas if e.get("ticker", "").upper() == target_ticker.upper()), None)
        if target_data:
            fallback_sector = target_data.get("sector", "")
            if fallback_sector:
                json_tickers = get_universe_by_sector(fallback_sector)[:30]

    if len(json_tickers) > MAX_JSON_TICKERS:
        json_tickers = json_tickers[:MAX_JSON_TICKERS]
    all_tickers.update(json_tickers)
    n_json = len(json_tickers)

    # Hard cap
    all_tickers_list = list(all_tickers)
    if len(all_tickers_list) > MAX_TOTAL_TICKERS:
        all_tickers_list = all_tickers_list[:MAX_TOTAL_TICKERS]

    print(f"   📊 Sources: Yahoo={n_yahoo} + JSON={n_json} + Manual={n_manual} → {len(all_tickers_list)} únicos")

    if not all_tickers_list:
        return []

    # ── FETCH PARALELO ──
    print(f"   ⬇ Bajando {len(all_tickers_list)} tickers | PARALLEL")
    empresas = fetch_many_parallel(all_tickers_list, max_workers=10)
    if not empresas:
        return []
    print(f"   ✅ {len(empresas)}/{len(all_tickers_list)} obtenidas")

    # ── AI FILTER — replaces static industry filter ──
    if HAS_AI_FILTER and target_industry and len(empresas) > 5:
        try:
            # Get target info for AI context
            target_name = target_ticker
            target_rev = 0
            for e in empresas:
                if e.get("Ticker", "").upper() == target_ticker.upper():
                    target_name = e.get("Empresa", target_ticker)
                    target_rev = e.get("Revenue ($mm)", 0)
                    break
            
            # If target not in candidates (e.g. sanitized out), use yfinance info
            if target_rev == 0:
                try:
                    _ti = yf.Ticker(target_ticker.upper()).info or {}
                    target_name = _ti.get("shortName", target_ticker)
                    target_rev = round((_ti.get("totalRevenue") or 0) / 1e6, 1)
                except:
                    pass

            pre_ai_count = len(empresas)
            empresas = ai_filter_comps_cached(
                target_ticker=target_ticker,
                target_name=target_name,
                target_industry=target_industry,
                target_revenue=target_rev,
                candidates=empresas,
            )
            print(f"   🧠 AI Filter: {pre_ai_count} → {len(empresas)} comps approved")
        except Exception as e:
            print(f"   ⚠️ AI Filter error (using unfiltered): {e}")
    elif not HAS_AI_FILTER and target_industry:
        # Fallback: basic industry keyword filter when AI is not available
        print(f"   ⚠️ No AI filter — using basic industry match")
        exact = [e for e in empresas if e.get("Industria") == target_industry]
        if len(exact) >= 5:
            empresas = exact

    return empresas


# ─────────────────────────────────────────────
# DIAGNOSTIC ENDPOINT
# ─────────────────────────────────────────────

@router.get("/comps/ai-status")
def ai_status():
    import os
    return {
        "HAS_AI_FILTER": HAS_AI_FILTER,
        "ANTHROPIC_KEY_SET": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "ANTHROPIC_KEY_PREFIX": (os.environ.get("ANTHROPIC_API_KEY") or "")[:10] + "...",
        "version": "v12",
    }


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@router.post("/comps")
def generar_comps(request: CompsRequest):
    try:
        empresa = request.empresa_override
        sector = request.sector_override
        revenue = request.revenue_override

        target_industry = None
        industry_key = None
        if empresa:
            # Use yfinance directly — avoid sanitize_empresa() rejection
            try:
                _info = yf.Ticker(empresa.upper()).info or {}
                target_industry = _info.get("industry")
                sector_yf = _info.get("sector", "")
                if target_industry:
                    industry_key = target_industry.lower().replace(" ", "-").replace("&", "and")
                print(f"\n📊 Comps: {empresa} | Industria: {target_industry} | Sector YF: {sector_yf} | Key: {industry_key}")
            except Exception as e:
                print(f"⚠️ Target lookup failed: {e}")

        empresas = discover_comps(empresa, target_industry, industry_key)

        region = request.region
        if region and region != "GLOBAL":
            region = COUNTRY_TO_REGION.get(region, region)
            empresas_region = [e for e in empresas if get_region_from_country(e.get("País") or e.get("Pais")) == region]
            empresas_resto = [e for e in empresas if get_region_from_country(e.get("País") or e.get("Pais")) != region]
            empresas = empresas_region + empresas_resto
            print(f"   🌎 Región {region}: {len(empresas_region)} | Resto: {len(empresas_resto)}")

        universe_pre_filter = list(empresas)
        empresas = clean_and_dedup(empresas, empresa, revenue, request.rango_min_pct / 100, request.rango_max_pct / 100)
        print(f"   📊 Final: {len(empresas)} comps (de {len(universe_pre_filter)} universe) para {empresa}")

        result = build_comps_response(
            empresas, empresa, sector, revenue,
            request.rango_min_pct / 100, request.rango_max_pct / 100
        )

        result["n_empresas_universe"] = len(universe_pre_filter)
        result["empresas_universe"] = universe_pre_filter
        result["target_industry"] = target_industry
        result["ai_filter_active"] = HAS_AI_FILTER
        result["discovery"] = {
            "yahoo_industry_key": industry_key,
            "sources": "Yahoo Industry + JSON + Manual Peers + Sector" + (" + AI Filter" if HAS_AI_FILTER else ""),
        }

        result = clean_inf(result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/comps/excel")
def descargar_excel(request: CompsRequest):
    try:
        empresa = request.empresa_override
        sector = request.sector_override
        revenue = request.revenue_override

        target_industry = None
        industry_key = None
        if empresa:
            try:
                _info = yf.Ticker(empresa.upper()).info or {}
                target_industry = _info.get("industry")
                if target_industry:
                    industry_key = target_industry.lower().replace(" ", "-").replace("&", "and")
            except:
                pass

        resultados = discover_comps(empresa, target_industry, industry_key)
        resultados = [r for r in resultados if r.get("Revenue ($mm)") is not None]

        target_upper = empresa.upper() if empresa else ""
        universe_raw = [
            r for r in resultados
            if r.get("Ticker", "").upper() != target_upper
            and r.get("Revenue ($mm)") and r.get("Revenue ($mm)") > 0
            and r.get("EV ($mm)") and r.get("EV ($mm)") > 0
        ]

        rev_map = {}
        for e in universe_raw:
            rev_key = round(e.get("Revenue ($mm)", 0) or 0, 0)
            t = e.get("Ticker", "")
            if rev_key not in rev_map:
                rev_map[rev_key] = e
            elif "." in rev_map[rev_key].get("Ticker", "") and "." not in t:
                rev_map[rev_key] = e
        universe = sorted(rev_map.values(), key=lambda x: x.get("Revenue ($mm)", 0) or 0, reverse=True)

        filtrados = clean_and_dedup(resultados, empresa, revenue, request.rango_min_pct / 100, request.rango_max_pct / 100)

        if not filtrados:
            raise HTTPException(status_code=500, detail="Sin datos")

        df_universe = pd.DataFrame(universe)
        df_filtrados = pd.DataFrame(filtrados)

        DEAL_CONFIG.update({
            "empresa_target": empresa, "sector": sector, "revenue_target": revenue,
            "rango_min_pct": request.rango_min_pct / 100, "rango_max_pct": request.rango_max_pct / 100,
            "analista": request.analista, "fecha": datetime.now().strftime("%d/%m/%Y"),
        })

        fname = f"Comps_{empresa.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        buffer = io.BytesIO()
        _generar_excel_buffer(df_filtrados, buffer, df_universe=df_universe)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'}
        )

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))