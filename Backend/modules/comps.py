"""
📊 COMPS MODULE v4 — FULL UNIVERSE + INDUSTRY FILTER
=====================================================
Baja TODAS las empresas del sector (cache = 2da vez instantáneo).
Filtra por industria Yahoo Finance ANTES de revenue range.
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
COUNTRY_TO_REGION = {
    "Argentina": "LATAM",
    "Brazil": "LATAM",
    "Mexico": "LATAM",
}
import requests

def discover_tickers(query: str):
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query}"

    try:
        res = requests.get(url, timeout=5)
        data = res.json()

        tickers = []

        for q in data.get("quotes", []):
            if q.get("quoteType") == "EQUITY":
                tickers.append(q["symbol"])

        return tickers

    except Exception:
        return []

def build_dynamic_universe_from_industry(industry: str):

    if not industry:
        return []

    # usar tu mapa (esto es clave)
    related_industries = INDUSTRY_GROUPS.get(industry, [industry])

    queries = list(set(related_industries))

    tickers = []

    for q in queries:
        tickers.extend(discover_tickers(q))

    return list(set(tickers))
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

_empresas_cache = None
def get_region_from_country(pais: str) -> str:
    if not pais:
        return "OTHER"

    # LATAM
    if pais in [
        "Argentina","Brazil","Mexico","Chile","Colombia","Peru","Uruguay",
        "Paraguay","Bolivia","Ecuador","Venezuela","Costa Rica","Panama",
        "Guatemala","Dominican Republic","El Salvador","Honduras","Nicaragua"
    ]:
        return "LATAM"

    # US
    if pais in ["United States", "USA", "United States of America"]:
        return "US"

    # EUROPE
    if pais in [
        "Germany","France","Spain","Italy","Luxembourg","Ireland",
        "Netherlands","Switzerland","Sweden","Norway","Denmark","Finland",
        "Belgium","Austria","Portugal","Poland","Czech Republic","Greece",
        "Hungary","Romania","Ukraine","United Kingdom","UK"
    ]:
        return "EU"

    # ASIA
    if pais in [
        "China","Hong Kong","Singapore","India","Japan","Indonesia",
        "South Korea","Taiwan","Thailand","Philippines","Malaysia",
        "Vietnam","Pakistan","Bangladesh","Saudi Arabia","UAE","Qatar","Israel"
    ]:
        return "ASIA"

    # AFRICA
    if pais in [
        "South Africa","Egypt","Nigeria","Kenya","Morocco","Ghana",
        "Ethiopia","Algeria","Tunisia"
    ]:
        return "AFRICA"

    # OCEANIA
    if pais in ["Australia", "New Zealand"]:
        return "OCEANIA"

    return "OTHER"
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

def filter_by_industry(empresas, target_industry):

    if not target_industry:
        return empresas

    similar = get_similar_industries(target_industry)
    similar_set = set(similar)

    # 1. exact match
    exact = [
        e for e in empresas
        if e.get("Industria") == target_industry
    ]

    # 2. similares
    sim = [
        e for e in empresas
        if e.get("Industria") in similar_set
    ]

    # 3. expansión (soft match)
    expansion_keywords = ["retail", "commerce", "marketplace"]

    expanded = [
        e for e in empresas
        if any(
            kw in (e.get("Industria") or "").lower()
            for kw in expansion_keywords
        )
    ]

    # combinar sin duplicados
    combined = []
    seen = set()

    for group in [exact, sim, expanded]:
        for e in group:
            if e["Ticker"] not in seen:
                combined.append(e)
                seen.add(e["Ticker"])

    print(f"Exact: {len(exact)} | Sim: {len(sim)} | Exp: {len(expanded)}")

    return combined[:25]  # 🔥 clave: límite sano

@router.post("/comps")
def generar_comps(request: CompsRequest):
    try:
        empresa = request.empresa_override
        sector = request.sector_override
        revenue = request.revenue_override

        # Detectar industria del target
        target_industry = None
        if empresa:
            td = get_financials_ttm(empresa.upper())
            if td and td.get("Industria"):
                target_industry = td["Industria"]
                print(f"\n📊 Comps: {empresa} | Industria: {target_industry}")

        # BUSCAR EN TODOS LOS SECTORES — no solo el seleccionado
        # La industria de Yahoo Finance es lo que importa, no el sector del JSON
        all_sectors = ["Technology", "Consumer", "Financials", "Industrials", "Energy", "Health Insurance", "Real Estate"]
        
        # base (lo que ya tenés)
        base_tickers = []
        for s in all_sectors:
            base_tickers.extend(get_universe_by_sector(s))

        # NUEVO: discovery dinámico desde Yahoo
        dynamic_tickers = build_dynamic_universe_from_industry(target_industry)

        print(f"🔎 Dynamic tickers: {len(dynamic_tickers)}")

        # combinar ambos
        all_tickers = list(set(base_tickers + dynamic_tickers))

        # limitar para no matar Yahoo
        all_tickers = all_tickers[:200]

        if not all_tickers:
            raise HTTPException(status_code=400, detail="No hay empresas cargadas")

        print(f"   Bajando {len(all_tickers)} tickers de TODOS los sectores | PARALLEL")
        empresas = fetch_many_parallel(all_tickers, max_workers=15)
        if not empresas:
            raise HTTPException(status_code=500, detail="No se pudieron obtener datos")
        print(f"   ✅ {len(empresas)}/{len(all_tickers)} obtenidas")

        # Filtrar por industria
        if target_industry:
            empresas = filter_by_industry(empresas, target_industry)

        # ── PRIORIDAD POR REGIÓN (NO FILTRO DURO) ───────────────

        region = request.region

        if region and region != "GLOBAL":

            region = COUNTRY_TO_REGION.get(region, region)

            # Separar región vs resto
            empresas_region = [
                e for e in empresas
                if get_region_from_country(e.get("Pais")) == region
            ]

            empresas_resto = [
                e for e in empresas
                if get_region_from_country(e.get("Pais")) != region
            ]

            # Concatenar: primero región, después resto
            empresas = empresas_region + empresas_resto

            print(f"🌎 Región {region}: {len(empresas_region)} | Resto: {len(empresas_resto)}")

            print(f"🌎 Priorizando región {region}")
        # EXCLUIR el target de sus propios comps
        target_upper = empresa.upper() if empresa else ""
        empresas = [e for e in empresas if e.get("Ticker", "").upper() != target_upper]
        
        # Deduplicar por empresa (BABA y 9988.HK son la misma)
        seen_names = set()
        unique_empresas = []
        for e in empresas:
            name = e.get("Empresa", "")
            if name not in seen_names:
                seen_names.add(name)
                unique_empresas.append(e)
        empresas = unique_empresas
        
        print(f"   📊 Final: {len(empresas)} comps únicos para {empresa}")

        result = build_comps_response(
            empresas, empresa, sector, revenue,
            request.rango_min_pct / 100, request.rango_max_pct / 100
        )
        result["target_industry"] = target_industry
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
        if empresa:
            td = get_financials_ttm(empresa.upper())
            if td and td.get("Industria"):
                target_industry = td["Industria"]

        # Buscar en TODOS los sectores
        all_sectors = ["Technology", "Consumer", "Financials", "Industrials", "Energy", "Health Insurance", "Real Estate"]
        all_tickers = []
        for s in all_sectors:
            all_tickers.extend(get_universe_by_sector(s))
        all_tickers = list(dict.fromkeys(all_tickers))

        resultados = fetch_many_parallel(all_tickers, max_workers=15)
        resultados = [r for r in resultados if r.get("Revenue ($mm)") is not None]

        if target_industry:
            resultados = filter_by_industry(resultados, target_industry)

        # Excluir target + deduplicar
        target_upper = empresa.upper() if empresa else ""
        resultados = [r for r in resultados if r.get("Ticker", "").upper() != target_upper]
        seen = set()
        unique = []
        for r in resultados:
            name = r.get("Empresa", "")
            if name not in seen:
                seen.add(name)
                unique.append(r)
        resultados = unique

        if not resultados:
            raise HTTPException(status_code=500, detail="Sin datos")

        df = pd.DataFrame(resultados)
        DEAL_CONFIG.update({
            "empresa_target": empresa, "sector": sector, "revenue_target": revenue,
            "rango_min_pct": request.rango_min_pct / 100, "rango_max_pct": request.rango_max_pct / 100,
            "analista": request.analista, "fecha": datetime.now().strftime("%d/%m/%Y"),
        })

        fname = f"Comps_{empresa.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        buffer = io.BytesIO()
        _generar_excel_buffer(df, buffer)
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