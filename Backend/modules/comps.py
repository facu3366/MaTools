"""
📊 COMPS MODULE v14 — FIXED DISCOVERY PIPELINE
=============================================================
FIX in v14 (over v13):
- INDUSTRY_TO_JSON_SECTORS removed — was injecting irrelevant companies (Walmart for Tesla)
- yf.Sector() SOURCE C removed — too broad, pollutes candidate pool  
- empresas.json SOURCE B now uses INDUSTRY_PEERS keys to find correct sector mapping
- sanitize_empresa: EBITDA negative filter relaxed for growth companies (keep if revenue > $1B)
- discover_comps sends ONLY industry-relevant candidates
- AI filter is refinement layer, not salvation layer
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
# INDUSTRY_PEERS — CURATED LISTS (ALWAYS INJECTED)
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
    "Telecom Services": ["T", "VZ", "TMUS", "CHTR", "CMCSA"],
    "Internet Content & Information": ["GOOGL", "META", "SNAP", "PINS", "RDDT", "MTCH"],
    "Information Technology Services": ["ACN", "IBM", "INFY", "WIT", "CTSH", "EPAM", "GLOB"],
    "Specialty Retail": ["HD", "LOW", "TJX", "ROST", "BURL", "ULTA", "BBY", "DKS"],
    "Medical Devices": ["MDT", "SYK", "BSX", "ABT", "ISRG", "EW", "BDX", "ZBH"],
    "Managed Health Care": ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"],
}

INDUSTRY_KEY_ALTERNATIVES = {
    "auto-manufacturers": ["automobiles", "automobile-manufacturers", "automotive"],
    "airlines": ["passenger-airlines"],
    "utilities---regulated-electric": ["utilities-regulated-electric", "electric-utilities"],
    "insurance---property-and-casualty": ["insurance-property-and-casualty", "property-casualty-insurance"],
    "residential-construction": ["homebuilders", "home-builders"],
    "consumer-electronics": ["consumer-electronics", "electronics"],
}

# ─────────────────────────────────────────────
# MAP: Yahoo industry → best INDUSTRY_PEERS key
# This replaces INDUSTRY_TO_JSON_SECTORS which was too broad
# ─────────────────────────────────────────────

INDUSTRY_ALIAS_MAP = {
    # Yahoo returns these → we map to our INDUSTRY_PEERS keys
    "Auto Manufacturers": "Auto Manufacturers",
    "Automobiles": "Auto Manufacturers",
    "Auto Parts": "Auto Parts",
    "Airlines": "Airlines",
    "Passenger Airlines": "Airlines",
    "Restaurants": "Restaurants",
    "Residential Construction": "Residential Construction",
    "Home Improvement Retail": "Home Improvement Retail",
    "Discount Stores": "Discount Stores",
    "Grocery Stores": "Grocery Stores",
    "Entertainment": "Entertainment",
    "Insurance - Property & Casualty": "Insurance - Property & Casualty",
    "Apparel Manufacturers": "Apparel Manufacturers",
    "Recreational Vehicles": "Recreational Vehicles",
    "Drug Manufacturers - General": "Drug Manufacturers - General",
    "Drug Manufacturers - Specialty & Generic": "Drug Manufacturers - General",
    "Biotechnology": "Biotechnology",
    "Consumer Electronics": "Consumer Electronics",
    "Footwear & Accessories": "Footwear & Accessories",
    "Health Care Plans": "Health Care Plans",
    "Managed Health Care": "Managed Health Care",
    "Internet Retail": "Internet Retail",
    "Software - Application": "Software - Application",
    "Software - Infrastructure": "Software - Infrastructure",
    "Semiconductors": "Semiconductors",
    "Semiconductor Equipment & Materials": "Semiconductors",
    "Banks - Diversified": "Banks - Diversified",
    "Banks - Regional": "Banks - Regional",
    "Oil & Gas Integrated": "Oil & Gas Integrated",
    "Oil & Gas E&P": "Oil & Gas E&P",
    "Telecom Services": "Telecom Services",
    "Internet Content & Information": "Internet Content & Information",
    "Information Technology Services": "Information Technology Services",
    "Specialty Retail": "Specialty Retail",
    "Medical Devices": "Medical Devices",
}

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

def clean_and_dedup(empresas: list[dict], target_ticker: str = "") -> list[dict]:
    """Clean data quality issues and deduplicate. Does NOT filter by revenue range."""
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
        # EBITDA negative: allow if revenue > $500M (growth companies like RIVN, LCID, NIO)
        ebitda = e.get("EBITDA ($mm)")
        if ebitda is not None and ebitda < 0 and rev < 500:
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

    # Dedup by revenue (prefer US-listed tickers over foreign)
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


def apply_revenue_filter(empresas: list[dict], target_revenue: float, rango_min_pct: float = 0.30, rango_max_pct: float = 3.0) -> list[dict]:
    """Apply revenue range filter separately from clean_and_dedup."""
    if not target_revenue or target_revenue <= 0:
        return empresas
    min_rev = target_revenue * rango_min_pct
    max_rev = target_revenue * rango_max_pct
    filtered = [e for e in empresas if min_rev <= e.get("Revenue ($mm)", 0) <= max_rev]
    removed = len(empresas) - len(filtered)
    if removed > 0:
        print(f"   📏 Revenue range ${min_rev:,.0f}-${max_rev:,.0f}mm: {removed} fuera de rango, {len(filtered)} pasan")
    return filtered


# ─────────────────────────────────────────────
# DISCOVER COMPS v14 — BULLETPROOF
# ─────────────────────────────────────────────

def discover_comps(target_ticker: str, target_industry: str, industry_key: str) -> list[dict]:
    all_tickers = set()

    # ── SOURCE A: Yahoo Finance Industry (most precise) ──
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

    # ── SOURCE B: Manual curated peers (ALWAYS ADDED) ──
    n_manual = 0
    peers_key = None
    
    # First try exact match
    if target_industry and target_industry in INDUSTRY_PEERS:
        peers_key = target_industry
    # Then try alias map
    elif target_industry and target_industry in INDUSTRY_ALIAS_MAP:
        peers_key = INDUSTRY_ALIAS_MAP[target_industry]
    
    if peers_key and peers_key in INDUSTRY_PEERS:
        manual = INDUSTRY_PEERS[peers_key]
        all_tickers.update(manual)
        n_manual = len(manual)
        print(f"   🔍 Source B: INDUSTRY_PEERS['{peers_key}'] → {n_manual} manual peers")

    # Also search partial matches in INDUSTRY_PEERS keys
    if target_industry:
        for key, peers in INDUSTRY_PEERS.items():
            if key != peers_key and (
                target_industry.lower() in key.lower() or 
                key.lower() in target_industry.lower()
            ):
                all_tickers.update(peers)
                print(f"   🔍 Source B (partial): '{key}' → {len(peers)} peers")

    # ── SOURCE C: REMOVED ──
    # yf.Sector() was too broad — "Consumer Cyclical" includes restaurants, hotels, retail
    # along with auto manufacturers. This polluted the candidate pool.
    # The AI filter can't fix garbage-in — better to send fewer, higher-quality candidates.

    # ── SOURCE D: REMOVED (was INDUSTRY_TO_JSON_SECTORS) ──
    # Mapping industries to empresas.json sectors was wrong.
    # "Auto Manufacturers" → "Consumer" brought Walmart, Nike, etc.

    # Hard cap
    all_tickers_list = list(all_tickers)
    if len(all_tickers_list) > MAX_TOTAL_TICKERS:
        all_tickers_list = all_tickers_list[:MAX_TOTAL_TICKERS]

    print(f"   📊 Sources: Yahoo={n_yahoo} + Manual={n_manual} → {len(all_tickers_list)} únicos")

    if not all_tickers_list:
        return []

    # ── FETCH PARALELO ──
    print(f"   ⬇ Bajando {len(all_tickers_list)} tickers | PARALLEL")
    empresas = fetch_many_parallel(all_tickers_list, max_workers=10)
    if not empresas:
        return []
    print(f"   ✅ {len(empresas)}/{len(all_tickers_list)} obtenidas")

    # ── AI FILTER (refinement, not salvation) ──
    if HAS_AI_FILTER and target_industry and len(empresas) > 5:
        try:
            target_name = target_ticker
            target_rev = 0
            for e in empresas:
                if e.get("Ticker", "").upper() == target_ticker.upper():
                    target_name = e.get("Empresa", target_ticker)
                    target_rev = e.get("Revenue ($mm)", 0)
                    break
            
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
        print(f"   ⚠️ No AI filter — using industry match fallback")
        # Try exact match first
        exact = [e for e in empresas if e.get("Industria") == target_industry]
        if len(exact) >= 5:
            empresas = exact
            print(f"   📌 Exact industry match: {len(exact)} comps")
        else:
            # Try partial match (e.g., "Auto" in "Auto Manufacturers" and "Auto Parts")
            partial = [e for e in empresas if target_industry.split(" - ")[0].split(" ")[0].lower() in (e.get("Industria") or "").lower()]
            if len(partial) >= 5:
                empresas = partial
                print(f"   📌 Partial industry match: {len(partial)} comps")

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
        "version": "v14",
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
            try:
                _info = yf.Ticker(empresa.upper()).info or {}
                target_industry = _info.get("industry")
                sector_yf = _info.get("sector", "")
                if target_industry:
                    industry_key = target_industry.lower().replace(" ", "-").replace("&", "and")
                print(f"\n📊 Comps: {empresa} | Industria: {target_industry} | Sector YF: {sector_yf} | Key: {industry_key}")
            except Exception as e:
                print(f"⚠️ Target lookup failed: {e}")

        # DISCOVER: get all industry candidates
        all_empresas = discover_comps(empresa, target_industry, industry_key)

        # REGION SORT
        region = request.region
        if region and region != "GLOBAL":
            region = COUNTRY_TO_REGION.get(region, region)
            empresas_region = [e for e in all_empresas if get_region_from_country(e.get("País") or e.get("Pais")) == region]
            empresas_resto = [e for e in all_empresas if get_region_from_country(e.get("País") or e.get("Pais")) != region]
            all_empresas = empresas_region + empresas_resto
            print(f"   🌎 Región {region}: {len(empresas_region)} | Resto: {len(empresas_resto)}")

        # CLEAN (data quality + dedup — NO revenue filter)
        universe = clean_and_dedup(all_empresas, empresa)
        
        # REVENUE FILTER (separate step — only for "filtradas" view)
        filtradas = apply_revenue_filter(universe, revenue, request.rango_min_pct / 100, request.rango_max_pct / 100)
        
        print(f"   📊 Universe: {len(universe)} | Filtradas: {len(filtradas)} para {empresa}")

        result = build_comps_response(
            filtradas, empresa, sector, revenue,
            request.rango_min_pct / 100, request.rango_max_pct / 100
        )

        # Override counts — universe is ALL industry comps, filtradas is revenue-filtered
        result["n_empresas_universe"] = len(universe)
        result["empresas_universe"] = clean_inf(universe)
        result["n_empresas_filtradas"] = len(filtradas)
        result["empresas_filtradas"] = clean_inf(filtradas)
        result["target_industry"] = target_industry
        result["ai_filter_active"] = HAS_AI_FILTER
        result["discovery"] = {
            "yahoo_industry_key": industry_key,
            "sources": "Yahoo Industry + Manual Peers" + (" + AI Filter" if HAS_AI_FILTER else ""),
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

        # Universe = all cleaned candidates (no revenue filter)
        universe = clean_and_dedup(resultados, empresa)
        
        # Filtradas = revenue range applied
        filtrados = apply_revenue_filter(universe, revenue, request.rango_min_pct / 100, request.rango_max_pct / 100)

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