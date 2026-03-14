"""
📊 FINANCIAL ENGINE v4 — TTM REAL + PRE-CALCULATED MULTIPLES
============================================================
Este módulo reemplaza get_financials() de comps_automatico.py

CAMBIOS CRÍTICOS vs v3:
1. TTM Revenue y EBITDA se calculan sumando los últimos 4 quarters reales
   (no confiamos en info["totalRevenue"] que puede ser annual)
2. Múltiplos (EV/Revenue, EV/EBITDA) se calculan en Python, no en Excel
3. Stats layer (mean/median) se calcula en el backend
4. Fallback: si quarterly no disponible, usa info[] con flag de warning

USO:
    from financial_engine import get_financials_ttm, calculate_comps_stats
"""

import yfinance as yf
import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 1. TTM CALCULATOR — EL CORE
# ─────────────────────────────────────────────

def _safe_round(val, decimals=1):
    """Round sin explotar si val es None."""
    if val is None or pd.isna(val):
        return None
    try:
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return None


def _sum_last_4q(series: pd.Series) -> Optional[float]:
    """
    Suma los últimos 4 quarters de una serie de yfinance.
    yfinance devuelve quarterly_financials con columnas = fechas (más reciente primero).
    
    Returns:
        float en raw (no dividido por 1M todavía) o None si no hay 4 quarters.
    """
    if series is None or series.empty:
        return None
    
    # Dropear NaN y tomar los últimos 4 valores disponibles
    valid = series.dropna()
    if len(valid) < 4:
        return None
    
    # yfinance quarterly: columnas ordenadas de más reciente a más antiguo
    # .iloc[:4] toma los 4 más recientes
    return float(valid.iloc[:4].sum())


def _quarters_available(series: pd.Series) -> int:
    """Cuántos quarters válidos hay."""
    if series is None or series.empty:
        return 0
    return len(series.dropna())


def get_financials_ttm(ticker: str) -> Optional[dict]:
    """
    Extrae datos financieros con TTM REAL calculado desde quarterly statements.
    
    LÓGICA:
    1. Intenta descargar quarterly_financials (income statement)
    2. Busca "Total Revenue" y suma últimos 4 quarters → TTM Revenue
    3. Busca "EBITDA" y suma últimos 4 quarters → TTM EBITDA
    4. Si EBITDA no está, intenta calcular: EBIT + Depreciation & Amortization
    5. Si quarterly falla → fallback a info[] con warning
    
    El dict de retorno incluye:
    - Todos los campos que necesita generar_excel() (mismas keys que antes)
    - Campos nuevos: ttm_method, quarters_used, ev_revenue, ev_ebitda
    - Múltiplos PRE-CALCULADOS (no depende de Excel)
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        
        if not info or info.get("quoteType") not in ("EQUITY",):
            return None

        def mm(val):
            """Convierte valor raw a millones."""
            if val is None or pd.isna(val):
                return None
            try:
                return round(float(val) / 1_000_000, 1)
            except (TypeError, ValueError):
                return None

        # ── IDENTIFICACIÓN ──
        empresa = info.get("shortName", ticker)
        pais    = info.get("country", "N/A")
        sector  = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        desc    = info.get("longBusinessSummary", "")
        if desc and len(desc) > 220:
            desc = desc[:217] + "..."

        # ── TTM REVENUE ──
        ttm_method = "quarterly"
        quarters_used = 0
        revenue_ttm_raw = None
        ebitda_ttm_raw = None

        try:
            qf = t.quarterly_financials  # columns = fechas, rows = line items
            
            if qf is not None and not qf.empty:
                # Revenue: buscar en orden de prioridad
                rev_keys = ["Total Revenue", "Revenue", "Net Revenue", "Operating Revenue"]
                for key in rev_keys:
                    if key in qf.index:
                        row = qf.loc[key]
                        quarters_used = _quarters_available(row)
                        if quarters_used >= 4:
                            revenue_ttm_raw = _sum_last_4q(row)
                            break

                # EBITDA: buscar directo primero
                ebitda_keys = ["EBITDA", "Normalized EBITDA"]
                for key in ebitda_keys:
                    if key in qf.index:
                        row = qf.loc[key]
                        if _quarters_available(row) >= 4:
                            ebitda_ttm_raw = _sum_last_4q(row)
                            break

                # Si no hay EBITDA directo, calcular: EBIT + D&A
                if ebitda_ttm_raw is None:
                    ebit_row = None
                    da_row = None
                    
                    for key in ["EBIT", "Operating Income"]:
                        if key in qf.index:
                            ebit_row = qf.loc[key]
                            break
                    
                    for key in ["Depreciation And Amortization", "Depreciation & Amortization",
                                "Reconciled Depreciation"]:
                        if key in qf.index:
                            da_row = qf.loc[key]
                            break
                    
                    if ebit_row is not None and da_row is not None:
                        if _quarters_available(ebit_row) >= 4 and _quarters_available(da_row) >= 4:
                            ebit_sum = _sum_last_4q(ebit_row)
                            da_sum = _sum_last_4q(da_row)
                            if ebit_sum is not None and da_sum is not None:
                                ebitda_ttm_raw = ebit_sum + abs(da_sum)

        except Exception as e:
            logger.warning(f"[{ticker}] quarterly_financials failed: {e}")

        # ── FALLBACK: si quarterly no dio resultados, usar info[] ──
        if revenue_ttm_raw is None:
            revenue_ttm_raw = info.get("totalRevenue")
            ttm_method = "info_fallback"
            quarters_used = 0

        if ebitda_ttm_raw is None:
            ebitda_ttm_raw = info.get("ebitda")

        # ── CONVERTIR A MILLONES ──
        revenue_mm = mm(revenue_ttm_raw)
        ebitda_mm  = mm(ebitda_ttm_raw)
        
        # Si revenue es None o 0, esta empresa no sirve para comps
        if not revenue_mm:
            return None

        # ── BALANCE SHEET (estos vienen de info[], no necesitan TTM) ──
        net_income_mm = mm(info.get("netIncomeToCommon"))
        gross_mm      = mm(info.get("grossProfits"))
        total_debt_mm = mm(info.get("totalDebt"))
        cash_mm       = mm(info.get("totalCash"))
        mkt_cap_mm    = mm(info.get("marketCap"))
        ev_mm         = mm(info.get("enterpriseValue"))

        # ── MÚLTIPLOS PRE-CALCULADOS ──
        # Esto antes se hacía con fórmulas Excel. Ahora Python los calcula.
        ev_revenue = None
        ev_ebitda  = None
        pe         = None
        
        if ev_mm and revenue_mm and revenue_mm > 0:
            ev_revenue = _safe_round(ev_mm / revenue_mm, 1)
        
        if ev_mm and ebitda_mm and ebitda_mm > 0:
            ev_ebitda = _safe_round(ev_mm / ebitda_mm, 1)
        
        if info.get("trailingPE"):
            pe = _safe_round(info["trailingPE"], 1)

        # ── MÁRGENES (calculados, no de info[]) ──
        ebitda_margin = None
        net_margin    = None
        gross_margin  = None
        
        if ebitda_mm and revenue_mm and revenue_mm > 0:
            ebitda_margin = _safe_round(ebitda_mm / revenue_mm * 100, 1)
        
        if net_income_mm and revenue_mm and revenue_mm > 0:
            net_margin = _safe_round(net_income_mm / revenue_mm * 100, 1)
        
        if gross_mm and revenue_mm and revenue_mm > 0:
            gross_margin = _safe_round(gross_mm / revenue_mm * 100, 1)

        # ── GROWTH ──
        rev_growth = None
        if info.get("revenueGrowth") is not None:
            rev_growth = _safe_round(info["revenueGrowth"] * 100, 1)

        return {
            # ── Identificación ──
            "Ticker":        ticker,
            "Empresa":       empresa,
            "País":          pais,
            "Sector":        sector,
            "Industria":     industry,
            "Descripción":   desc,
            
            # ── Financials (TTM) ──
            "Revenue ($mm)": revenue_mm,
            "EBITDA ($mm)":  ebitda_mm,
            "Net Inc ($mm)": net_income_mm,
            "Gross ($mm)":   gross_mm,
            "Deuda ($mm)":   total_debt_mm,
            "Cash ($mm)":    cash_mm,
            "Mkt Cap ($mm)": mkt_cap_mm,
            "EV ($mm)":      ev_mm,
            
            # ── Múltiplos PRE-CALCULADOS ──
            "EV/Revenue":    ev_revenue,
            "EV/EBITDA":     ev_ebitda,
            "P/E":           pe,
            
            # ── Márgenes ──
            "EBITDA Mg%":    ebitda_margin,
            "Net Mg%":       net_margin,
            "Gross Mg%":     gross_margin,
            "Rev Growth %":  rev_growth,
            
            # ── Metadata (para el frontend y debugging) ──
            "Empleados":     info.get("fullTimeEmployees"),
            "ttm_method":    ttm_method,      # "quarterly" o "info_fallback"
            "quarters_used": quarters_used,    # 4 = TTM real, 0 = fallback
        }

    except Exception as e:
        logger.warning(f"[{ticker}] get_financials_ttm failed: {e}")
        return None


# ─────────────────────────────────────────────
# 2. STATS LAYER — MEAN + MEDIAN
# ─────────────────────────────────────────────

def calculate_comps_stats(empresas: list[dict]) -> dict:
    """
    Calcula Mean y Median de los múltiplos y métricas del set de comps.
    
    REGLAS:
    - Solo usa valores no-None para cada métrica
    - Si una empresa no tiene EBITDA, no se incluye en el promedio de EV/EBITDA
      (no rompe el cálculo)
    - Devuelve dict con "mean" y "median" para cada métrica
    
    Args:
        empresas: lista de dicts retornados por get_financials_ttm()
    
    Returns:
        {
            "n_empresas": 25,
            "metrics": {
                "EV/Revenue": {"mean": 3.2, "median": 2.8, "min": 0.5, "max": 12.1, "count": 24},
                "EV/EBITDA":  {"mean": 14.5, "median": 12.3, ...},
                ...
            }
        }
    """
    if not empresas:
        return {"n_empresas": 0, "metrics": {}}

    df = pd.DataFrame(empresas)
    
    metric_keys = [
        "Revenue ($mm)", "EBITDA ($mm)", "Net Inc ($mm)", "EV ($mm)",
        "Mkt Cap ($mm)", "EV/Revenue", "EV/EBITDA", "P/E",
        "EBITDA Mg%", "Net Mg%", "Gross Mg%", "Rev Growth %",
    ]
    
    stats = {}
    for key in metric_keys:
        if key not in df.columns:
            continue
        
        series = pd.to_numeric(df[key], errors="coerce").dropna()
        
        if len(series) == 0:
            stats[key] = {"mean": None, "median": None, "min": None, "max": None, "count": 0}
            continue
        
        stats[key] = {
            "mean":   _safe_round(series.mean(), 2),
            "median": _safe_round(series.median(), 2),
            "min":    _safe_round(series.min(), 2),
            "max":    _safe_round(series.max(), 2),
            "count":  int(len(series)),
        }
    
    return {
        "n_empresas": len(empresas),
        "metrics": stats,
    }


# ─────────────────────────────────────────────
# 3. COMPS RESPONSE BUILDER
# ─────────────────────────────────────────────

def build_comps_response(
    empresas: list[dict],
    empresa_target: str,
    sector: str,
    revenue_target: float,
    rango_min_pct: float = 0.3,
    rango_max_pct: float = 3.0,
) -> dict:
    """
    Construye la respuesta completa de comps para el endpoint /comps.
    
    Incluye:
    - Universe completo con stats
    - Filtradas por revenue range con stats separadas
    - TTM warnings si hay empresas con fallback
    
    Returns:
        dict listo para JSON response
    """
    df = pd.DataFrame(empresas)
    
    # Filtrar por revenue range
    rev_min = revenue_target * rango_min_pct
    rev_max = revenue_target * rango_max_pct
    
    mask = (
        df["Revenue ($mm)"].notna() &
        (df["Revenue ($mm)"] >= rev_min) &
        (df["Revenue ($mm)"] <= rev_max)
    )
    
    filtradas = df[mask].to_dict("records")
    
    # Stats de todo el universe
    stats_universe = calculate_comps_stats(empresas)
    
    # Stats solo de las filtradas
    stats_filtradas = calculate_comps_stats(filtradas)
    
    # TTM quality check
    n_quarterly = sum(1 for e in empresas if e.get("ttm_method") == "quarterly")
    n_fallback  = sum(1 for e in empresas if e.get("ttm_method") == "info_fallback")
    
    ttm_quality = {
        "quarterly_ttm": n_quarterly,
        "info_fallback": n_fallback,
        "pct_real_ttm": round(n_quarterly / len(empresas) * 100, 1) if empresas else 0,
    }
    
    return {
        "empresa_target":       empresa_target,
        "sector":               sector,
        "revenue_target":       revenue_target,
        "rango_revenue":        {"min_mm": round(rev_min, 1), "max_mm": round(rev_max, 1)},
        "n_empresas_universe":  len(empresas),
        "n_empresas_filtradas": len(filtradas),
        "ttm_quality":          ttm_quality,
        "stats_universe":       stats_universe,
        "stats_filtradas":      stats_filtradas,
        "empresas_filtradas":   filtradas,
        "empresas_universe":    empresas,
    }