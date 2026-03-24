"""
📊 COMPS MODULE v7 — DIRECTED DISCOVERY + OUTLIER KILL
=======================================================
Source A: yf.Industry(industryKey).top_companies → Yahoo Finance peers (dynamic)
Source B: empresas.json filtered by INDUSTRY → limited fallback (not full sector dump)
Smart filter: sanitize + clean_and_dedup + revenue range + dedup

v7 CAMBIOS vs v6:
- discover_comps baja ~40-60 tickers en vez de 609 (15-25 seg vs 3:20 min)
- INDUSTRY_TO_JSON_SECTORS: mapa industria → sectores JSON con caps
- Hard cap de 80 tickers totales
- clean_and_dedup con caps consistentes (40x EV/Rev, 75x EV/EBITDA)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

import pathlib
import json
import pandas as pd
import io
import traceback
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

router = APIRouter()
logger = logging.getLogger(__name__)
import math

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
# INDUSTRY GROUPS (para filter_by_industry)
# ─────────────────────────────────────────────

INDUSTRY_GROUPS = {
    "Internet Retail": ["Internet Retail", "Specialty Retail", "Broadline Retail"],
    "Broadline Retail": ["Broadline Retail", "Internet Retail", "Specialty Retail"],
    "Software - Application": ["Software - Application", "Software - Infrastructure", "Information Technology Services"],
    "Software - Infrastructure": ["Software - Infrastructure", "Software - Application", "Information Technology Services"],
    "Information Technology Services": ["Information Technology Services", "Software - Application", "Software - Infrastructure", "Consulting Services"],
    "Semiconductors": ["Semiconductors", "Semiconductor Equipment & Materials", "Electronic Components"],
    "Semiconductor Equipment & Materials": ["Semiconductor Equipment & Materials", "Semiconductors"],
    "Internet Content & Information": ["Internet Content & Information", "Internet Retail", "Electronic Gaming & Multimedia"],
    "Electronic Gaming & Multimedia": ["Electronic Gaming & Multimedia", "Internet Content & Information", "Entertainment"],
    "Consumer Electronics": ["Consumer Electronics", "Internet Retail", "Communication Equipment"],
    "Telecom Services": ["Telecom Services", "Communication Equipment"],
    "Communication Equipment": ["Communication Equipment", "Telecom Services"],
    "Credit Services": ["Credit Services", "Financial Data & Stock Exchanges", "Capital Markets"],
    "Financial Data & Stock Exchanges": ["Financial Data & Stock Exchanges", "Capital Markets", "Credit Services"],
    "Capital Markets": ["Capital Markets", "Financial Data & Stock Exchanges", "Asset Management"],
    "Asset Management": ["Asset Management", "Capital Markets"],
    "Banks - Diversified": ["Banks - Diversified", "Banks - Regional"],
    "Banks - Regional": ["Banks - Regional", "Banks - Diversified"],
    "Insurance - Diversified": ["Insurance - Diversified", "Insurance - Life", "Insurance Brokers", "Insurance - Property & Casualty"],
    "Insurance - Life": ["Insurance - Life", "Insurance - Diversified"],
    "Insurance Brokers": ["Insurance Brokers", "Insurance - Diversified"],
    "Health Care Plans": ["Health Care Plans", "Insurance - Diversified", "Medical Care Facilities"],
    "Oil & Gas Integrated": ["Oil & Gas Integrated", "Oil & Gas E&P", "Oil & Gas Refining & Marketing"],
    "Oil & Gas E&P": ["Oil & Gas E&P", "Oil & Gas Integrated", "Oil & Gas Midstream"],
    "Oil & Gas Refining & Marketing": ["Oil & Gas Refining & Marketing", "Oil & Gas Integrated"],
    "Oil & Gas Midstream": ["Oil & Gas Midstream", "Oil & Gas E&P", "Oil & Gas Integrated"],
    "Oil & Gas Equipment & Services": ["Oil & Gas Equipment & Services", "Oil & Gas E&P"],
    "Drug Manufacturers - General": ["Drug Manufacturers - General", "Drug Manufacturers - Specialty & Generic", "Biotechnology"],
    "Drug Manufacturers - Specialty & Generic": ["Drug Manufacturers - Specialty & Generic", "Drug Manufacturers - General", "Biotechnology"],
    "Biotechnology": ["Biotechnology", "Drug Manufacturers - General", "Drug Manufacturers - Specialty & Generic"],
    "Medical Devices": ["Medical Devices", "Medical Instruments & Supplies", "Health Care Equipment & Services"],
    "Medical Care Facilities": ["Medical Care Facilities", "Health Care Plans", "Medical Devices"],
    "Medical Instruments & Supplies": ["Medical Instruments & Supplies", "Medical Devices", "Diagnostics & Research"],
    "Diagnostics & Research": ["Diagnostics & Research", "Medical Instruments & Supplies", "Biotechnology"],
    "Medical Distribution": ["Medical Distribution", "Medical Instruments & Supplies", "Health Care Plans"],
    "Discount Stores": ["Discount Stores", "Department Stores", "Grocery Stores"],
    "Grocery Stores": ["Grocery Stores", "Discount Stores"],
    "Home Improvement Retail": ["Home Improvement Retail", "Specialty Retail", "Building Products & Equipment"],
    "Specialty Retail": ["Specialty Retail", "Internet Retail", "Apparel Retail"],
    "Apparel Retail": ["Apparel Retail", "Specialty Retail", "Footwear & Accessories"],
    "Luxury Goods": ["Luxury Goods", "Apparel Retail", "Footwear & Accessories"],
    "Restaurants": ["Restaurants", "Packaged Foods", "Food Distribution"],
    "Packaged Foods": ["Packaged Foods", "Beverages - Non-Alcoholic", "Household & Personal Products"],
    "Beverages - Non-Alcoholic": ["Beverages - Non-Alcoholic", "Packaged Foods", "Beverages - Brewers"],
    "Auto Manufacturers": ["Auto Manufacturers", "Auto Parts", "Recreational Vehicles"],
    "Aerospace & Defense": ["Aerospace & Defense", "Specialty Industrial Machinery"],
    "Specialty Industrial Machinery": ["Specialty Industrial Machinery", "Diversified Industrials", "Farm & Heavy Construction Machinery"],
    "Farm & Heavy Construction Machinery": ["Farm & Heavy Construction Machinery", "Specialty Industrial Machinery"],
    "Railroads": ["Railroads", "Trucking", "Integrated Freight & Logistics"],
    "Trucking": ["Trucking", "Integrated Freight & Logistics", "Railroads"],
    "Integrated Freight & Logistics": ["Integrated Freight & Logistics", "Trucking", "Air Freight & Logistics"],
    "Airlines": ["Airlines", "Airports & Air Services"],
    "Waste Management": ["Waste Management", "Environmental Services"],
    "REIT - Industrial": ["REIT - Industrial", "REIT - Diversified", "REIT - Office"],
    "REIT - Residential": ["REIT - Residential", "REIT - Diversified"],
    "REIT - Retail": ["REIT - Retail", "REIT - Diversified"],
    "REIT - Office": ["REIT - Office", "REIT - Industrial", "REIT - Diversified"],
    "REIT - Specialty": ["REIT - Specialty", "REIT - Diversified", "REIT - Industrial"],
    "Real Estate Services": ["Real Estate Services", "Real Estate - Development", "REIT - Diversified"],
    "Utilities - Regulated Electric": ["Utilities - Regulated Electric", "Utilities - Diversified", "Utilities - Renewable"],
    "Utilities - Renewable": ["Utilities - Renewable", "Utilities - Regulated Electric", "Solar"],
    "Solar": ["Solar", "Utilities - Renewable"],
    "Lodging": ["Lodging", "Resorts & Casinos", "Travel Services"],
    "Resorts & Casinos": ["Resorts & Casinos", "Lodging", "Entertainment"],
    "Travel Services": ["Travel Services", "Lodging", "Internet Content & Information"],
    "Entertainment": ["Entertainment", "Electronic Gaming & Multimedia", "Media - Diversified"],
}

def get_similar_industries(industry: str) -> list[str]:
    if not industry:
        return []
    if industry in INDUSTRY_GROUPS:
        return INDUSTRY_GROUPS[industry]
    il = industry.lower()
    for key, values in INDUSTRY_GROUPS.items():
        if key.lower() in il or il in key.lower():
            return values
    return [industry]

MIN_COMPS = 10

def filter_by_industry(empresas: list[dict], target_industry: str) -> list[dict]:
    if not target_industry:
        return empresas
    similar = get_similar_industries(target_industry)
    similar_set = set(similar)
    exact = [e for e in empresas if e.get("Industria") == target_industry]
    if len(exact) >= MIN_COMPS:
        return exact
    sim = [e for e in empresas if e.get("Industria") in similar_set]
    if len(sim) >= MIN_COMPS:
        return sim
    return sorted(empresas, key=lambda e: (0 if e.get("Industria") in similar_set else 1))[:30]


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
# CLEAN & DEDUP (caps consistentes con sanitize_empresa)
# ─────────────────────────────────────────────

def clean_and_dedup(empresas: list[dict], target_ticker: str = "", target_revenue: float = 0) -> list[dict]:
    """
    Limpia y deduplica la lista de empresas para comps.
    
    Filtros (en orden):
    1. Excluir la empresa target
    2. Revenue > 0 y EV > 0
    3. EBITDA no negativo (no sirve para valuation)
    4. EV/Revenue <= 40x (consistente con sanitize_empresa)
    5. EV/EBITDA <= 75x (consistente con sanitize_empresa)
    6. Gross Margin <= 100% (imposible)
    7. Revenue range relativo al target (2% - 50x)
    8. Dedup por revenue (preferir ticker US sobre extranjero)
    """
    target_upper = target_ticker.upper() if target_ticker else ""
    
    # 1. Excluir target
    empresas = [e for e in empresas if e.get("Ticker", "").upper() != target_upper]

    clean = []
    for e in empresas:
        ticker = e.get("Ticker", "")
        rev = e.get("Revenue ($mm)")
        ev = e.get("EV ($mm)")

        # 2. Revenue y EV deben existir y ser positivos
        if not rev or rev <= 0:
            continue
        if not ev or ev <= 0:
            print(f"   ⚠️ Skip {ticker} — EV negativo o inexistente")
            continue

        # 3. EBITDA negativo
        ebitda = e.get("EBITDA ($mm)")
        if ebitda is not None and ebitda < 0:
            print(f"   ⚠️ Skip {ticker} — EBITDA negativo ({ebitda})")
            continue

        # 4. EV/Revenue > 40x
        ev_rev = ev / rev
        if ev_rev > 40:
            print(f"   ⚠️ Skip {ticker} — EV/Rev {ev_rev:.1f}x > 40x")
            continue

        # 5. EV/EBITDA > 75x
        if ebitda is not None and ebitda > 0:
            ev_ebitda = ev / ebitda
            if ev_ebitda > 75:
                print(f"   ⚠️ Skip {ticker} — EV/EBITDA {ev_ebitda:.1f}x > 75x")
                continue

        # 6. Gross Margin > 100%
        gross = e.get("Gross ($mm)")
        if gross and rev > 0:
            gm = gross / rev * 100
            if gm > 100:
                print(f"   ⚠️ Skip {ticker} — Gross Margin {gm:.1f}% > 100%")
                continue

        clean.append(e)

    # 7. Revenue range relativo al target
    if target_revenue and target_revenue > 0:
        min_rev = target_revenue * 0.02
        max_rev = target_revenue * 50
        before = len(clean)
        clean = [e for e in clean if min_rev <= e.get("Revenue ($mm)", 0) <= max_rev]
        filtered = before - len(clean)
        if filtered > 0:
            print(f"   📏 Revenue range ${min_rev:,.0f}-${max_rev:,.0f}mm: {filtered} fuera de rango")

    # 8. Dedup por revenue (preferir US ticker)
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
            elif "." not in existing_ticker and "." not in ticker and len(ticker) < len(existing_ticker):
                revenue_map[rev_key] = e

    result = list(revenue_map.values())
    result.sort(key=lambda e: e.get("Revenue ($mm)", 0), reverse=True)
    print(f"   🧹 Resultado: {len(result)} comps limpios (de {len(empresas)} candidatos)")
    result = clean_inf(result)
    return result

# ─────────────────────────────────────────────
# INDUSTRY → JSON SECTORS MAP (para discover_comps)
# ─────────────────────────────────────────────
# Dado que empresas.json solo tiene "sector" (no "industry"),
# este mapa dice: para cada industria de Yahoo, qué sectores
# del JSON son relevantes y cuántos tickers máximo bajar.

INDUSTRY_TO_JSON_SECTORS = {
    # E-COMMERCE / RETAIL
    "Internet Retail":          [("Consumer", 15), ("Technology", 10)],
    "Broadline Retail":         [("Consumer", 20)],
    "Specialty Retail":         [("Consumer", 20)],
    "Apparel Retail":           [("Consumer", 15)],
    "Discount Stores":          [("Consumer", 15)],
    "Grocery Stores":           [("Consumer", 15)],
    "Home Improvement Retail":  [("Consumer", 15)],
    "Luxury Goods":             [("Consumer", 15)],

    # SOFTWARE / TECH
    "Software - Application":           [("Technology", 25)],
    "Software - Infrastructure":        [("Technology", 25)],
    "Information Technology Services":  [("Technology", 25)],
    "Internet Content & Information":   [("Technology", 20)],
    "Electronic Gaming & Multimedia":   [("Technology", 20)],
    "Consumer Electronics":             [("Technology", 20)],

    # SEMICONDUCTORS
    "Semiconductors":                       [("Technology", 20)],
    "Semiconductor Equipment & Materials":  [("Technology", 15)],

    # TELECOM
    "Telecom Services":         [("Technology", 15)],
    "Communication Equipment":  [("Technology", 15)],

    # FINANCIALS
    "Credit Services":                      [("Financials", 25)],
    "Financial Data & Stock Exchanges":     [("Financials", 20)],
    "Capital Markets":                      [("Financials", 25)],
    "Asset Management":                     [("Financials", 20)],
    "Banks - Diversified":                  [("Financials", 25)],
    "Banks - Regional":                     [("Financials", 25)],
    "Insurance - Diversified":              [("Financials", 20), ("Health Insurance", 10)],
    "Insurance - Life":                     [("Financials", 20)],
    "Insurance Brokers":                    [("Financials", 15)],

    # HEALTH
    "Health Care Plans":                [("Health Insurance", 25)],
    "Medical Devices":                  [("Health Insurance", 20)],
    "Medical Care Facilities":          [("Health Insurance", 20)],
    "Drug Manufacturers - General":     [("Health Insurance", 25)],
    "Biotechnology":                    [("Health Insurance", 25)],
    "Diagnostics & Research":           [("Health Insurance", 15)],
    "Medical Distribution":             [("Health Insurance", 15)],

    # ENERGY
    "Oil & Gas Integrated":             [("Energy", 25)],
    "Oil & Gas E&P":                    [("Energy", 25)],
    "Oil & Gas Refining & Marketing":   [("Energy", 20)],
    "Oil & Gas Midstream":              [("Energy", 20)],
    "Oil & Gas Equipment & Services":   [("Energy", 15)],

    # INDUSTRIALS
    "Aerospace & Defense":              [("Industrials", 25)],
    "Specialty Industrial Machinery":   [("Industrials", 20)],
    "Railroads":                        [("Industrials", 15)],
    "Trucking":                         [("Industrials", 15)],
    "Integrated Freight & Logistics":   [("Industrials", 15)],
    "Airlines":                         [("Industrials", 15)],
    "Waste Management":                 [("Industrials", 15)],
    "Auto Manufacturers":               [("Consumer", 15), ("Industrials", 10)],
    "Farm & Heavy Construction Machinery": [("Industrials", 15)],

    # REAL ESTATE
    "REIT - Industrial":        [("Real Estate", 20)],
    "REIT - Residential":       [("Real Estate", 20)],
    "REIT - Retail":            [("Real Estate", 20)],
    "REIT - Office":            [("Real Estate", 20)],
    "REIT - Specialty":         [("Real Estate", 20)],
    "Real Estate Services":     [("Real Estate", 20)],

    # CONSUMER
    "Restaurants":              [("Consumer", 20)],
    "Packaged Foods":           [("Consumer", 20)],
    "Beverages - Non-Alcoholic": [("Consumer", 15)],
    "Lodging":                  [("Consumer", 15)],
    "Resorts & Casinos":        [("Consumer", 15)],
    "Travel Services":          [("Consumer", 15)],
    "Entertainment":            [("Consumer", 15), ("Technology", 10)],

    # UTILITIES
    "Utilities - Regulated Electric":   [("Energy", 20)],
    "Utilities - Renewable":            [("Energy", 20)],
    "Solar":                            [("Energy", 15)],
}

MAX_JSON_TICKERS = 40
MAX_TOTAL_TICKERS = 80


# ─────────────────────────────────────────────
# DISCOVER COMPS — DIRECTED SEARCH
# ─────────────────────────────────────────────

def discover_comps(target_ticker: str, target_industry: str, industry_key: str) -> list[dict]:
    """
    Descubre empresas comparables con búsqueda DIRIGIDA.
    
    Estrategia:
    1. Yahoo Industry peers (~15 tickers) → siempre se bajan
    2. JSON fallback → SOLO sectores relevantes, con cap por sector
    3. Hard cap de 80 tickers totales
    
    Para MELI (Internet Retail):
      Yahoo: 15 peers (AMZN, DASH, EBAY, CPNG, etc.)
      JSON:  15 de Consumer + 10 de Technology = 25
      Total: ~40 tickers en vez de 609
    """
    all_tickers = set()

    # ── SOURCE A: Yahoo Finance Industry (~15 tickers) ──
    yahoo_tickers = discover_industry_peers(industry_key)
    all_tickers.update(yahoo_tickers)
    n_yahoo = len(yahoo_tickers)

    # ── SOURCE B: empresas.json — FILTRADO por industria ──
    json_tickers = []
    
    if target_industry and target_industry in INDUSTRY_TO_JSON_SECTORS:
        # Tenemos mapping específico → usar solo los sectores relevantes con caps
        sector_limits = INDUSTRY_TO_JSON_SECTORS[target_industry]
        for sector_name, max_from_sector in sector_limits:
            sector_tickers = get_universe_by_sector(sector_name)
            json_tickers.extend(sector_tickers[:max_from_sector])
    elif target_industry:
        # Industria no mapeada → fallback conservador
        similar = get_similar_industries(target_industry)
        print(f"   ⚠️ Industria '{target_industry}' sin mapping directo. Similar: {similar[:3]}")
        # Usar el sector del target en empresas.json como fallback
        all_empresas = load_empresas()
        target_data = next((e for e in all_empresas if e.get("ticker", "").upper() == target_ticker.upper()), None)
        if target_data:
            fallback_sector = target_data.get("sector", "")
            if fallback_sector:
                json_tickers = get_universe_by_sector(fallback_sector)[:30]
    
    # Aplicar hard cap al JSON
    if len(json_tickers) > MAX_JSON_TICKERS:
        json_tickers = json_tickers[:MAX_JSON_TICKERS]
    
    all_tickers.update(json_tickers)
    n_json = len(json_tickers)

    # Hard cap total
    all_tickers = list(all_tickers)
    if len(all_tickers) > MAX_TOTAL_TICKERS:
        excess = len(all_tickers) - MAX_TOTAL_TICKERS
        print(f"   ⚠️ Hard cap: recortando {excess} tickers (de {len(all_tickers)} a {MAX_TOTAL_TICKERS})")
        all_tickers = all_tickers[:MAX_TOTAL_TICKERS]

    print(f"   📊 Sources: Yahoo={n_yahoo} + JSON={n_json} → {len(all_tickers)} únicos (cap={MAX_TOTAL_TICKERS})")

    if not all_tickers:
        return []

    # ── FETCH PARALELO ──
    print(f"   ⬇ Bajando {len(all_tickers)} tickers | PARALLEL")
    empresas = fetch_many_parallel(all_tickers, max_workers=10)
    if not empresas:
        return []
    print(f"   ✅ {len(empresas)}/{len(all_tickers)} obtenidas")

    # ── FILTRO POR INDUSTRIA ──
    if target_industry:
        empresas = filter_by_industry(empresas, target_industry)

    return empresas


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
            td = get_financials_ttm(empresa.upper())
            if td:
                target_industry = td.get("Industria")
                if target_industry:
                    industry_key = target_industry.lower().replace(" ", "-").replace("&", "and")
                print(f"\n📊 Comps: {empresa} | Industria: {target_industry} | Key: {industry_key}")

        empresas = discover_comps(empresa, target_industry, industry_key)

        region = request.region
        if region and region != "GLOBAL":
            region = COUNTRY_TO_REGION.get(region, region)
            empresas_region = [e for e in empresas if get_region_from_country(e.get("País") or e.get("Pais")) == region]
            empresas_resto = [e for e in empresas if get_region_from_country(e.get("País") or e.get("Pais")) != region]
            empresas = empresas_region + empresas_resto
            print(f"   🌎 Región {region}: {len(empresas_region)} | Resto: {len(empresas_resto)}")

        universe_pre_filter = list(empresas)  # guardar universe ANTES de filtrar
        empresas = clean_and_dedup(empresas, empresa, revenue)
        print(f"   📊 Final: {len(empresas)} comps (de {len(universe_pre_filter)} universe) para {empresa}")

        result = build_comps_response(
            empresas, empresa, sector, revenue,
            request.rango_min_pct / 100, request.rango_max_pct / 100
        )

        result["n_empresas_universe"] = len(universe_pre_filter)
        result["empresas_universe"] = universe_pre_filter
        result["target_industry"] = target_industry
        result["discovery"] = {
            "yahoo_industry_key": industry_key,
            "sources": "Yahoo Industry + empresas.json"
        }

        # limpio inf / nan antes de devolver
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
            td = get_financials_ttm(empresa.upper())
            if td:
                target_industry = td.get("Industria")
                if target_industry:
                    industry_key = target_industry.lower().replace(" ", "-").replace("&", "and")

        resultados = discover_comps(empresa, target_industry, industry_key)
        resultados = [r for r in resultados if r.get("Revenue ($mm)") is not None]
        # Universe: solo excluir target + dedup, SIN filtros de calidad
        target_upper = empresa.upper() if empresa else ""
        universe_raw = [
    r for r in resultados 
    if r.get("Ticker", "").upper() != target_upper
    and r.get("Revenue ($mm)") and r.get("Revenue ($mm)") > 0
    and r.get("EV ($mm)") and r.get("EV ($mm)") > 0
]
        # Dedup simple por revenue
        rev_map = {}
        for e in universe_raw:
            rev_key = round(e.get("Revenue ($mm)", 0) or 0, 0)
            t = e.get("Ticker", "")
            if rev_key not in rev_map:
                rev_map[rev_key] = e
            elif "." in rev_map[rev_key].get("Ticker", "") and "." not in t:
                rev_map[rev_key] = e
        universe = sorted(rev_map.values(), key=lambda x: x.get("Revenue ($mm)", 0) or 0, reverse=True)

        # Comps FILTRADOS (con revenue range) para Hoja 2
        filtrados = clean_and_dedup(resultados, empresa, revenue)

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