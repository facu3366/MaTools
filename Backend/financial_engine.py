"""
📊 FINANCIAL ENGINE v6 — CACHE + PARALLEL + OUTLIER KILL
=========================================================
CAMBIOS vs v5:
1. FIX CRÍTICO: FX conversion ahora se ejecuta DESPUÉS de definir todas las variables
2. NUEVO: sanitize_empresa() — filtra outliers ANTES de que lleguen al Excel
3. NUEVO: Gross Margin > 100% = descarte automático
4. Cache y parallel fetch sin cambios

RESULTADO: BUKA.JK, NYKAA.NS, NPN.JO, y cualquier empresa con datos
en moneda local o múltiplos absurdos se eliminan automáticamente.
"""

import yfinance as yf
import pandas as pd
from typing import Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading
import math

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 0. CACHE EN MEMORIA (Thread-safe)
# ─────────────────────────────────────────────

_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL_HOURS = 6


def _cache_get(ticker: str) -> Optional[dict]:
    with _cache_lock:
        entry = _cache.get(ticker)
        if entry is None:
            return None
        if datetime.now() - entry["timestamp"] > timedelta(hours=CACHE_TTL_HOURS):
            del _cache[ticker]
            return None
        return entry["data"]


def _cache_set(ticker: str, data: Optional[dict]):
    with _cache_lock:
        _cache[ticker] = {
            "data": data,
            "timestamp": datetime.now(),
        }


def cache_stats() -> dict:
    with _cache_lock:
        return {
            "cached_tickers": len(_cache),
            "tickers": list(_cache.keys()),
        }


# ─────────────────────────────────────────────
# 1. HELPERS
# ─────────────────────────────────────────────

def _safe_round(val, decimals=1):
    if val is None or pd.isna(val):
        return None
    try:
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return None


def _sum_last_4q(series: pd.Series) -> Optional[float]:
    if series is None or series.empty:
        return None
    valid = series.dropna()
    if len(valid) < 4:
        return None
    return float(valid.iloc[:4].sum())


def _quarters_available(series: pd.Series) -> int:
    if series is None or series.empty:
        return 0
    return len(series.dropna())


# ─────────────────────────────────────────────
# 2. SANITIZE — MATA OUTLIERS ANTES DEL EXCEL
# ─────────────────────────────────────────────

def sanitize_empresa(data: dict) -> Optional[dict]:
    """
    Valida que los datos de una empresa sean razonables.
    Retorna None si la empresa debe descartarse.
    
    Reglas:
    - Revenue debe existir y ser > 0
    - EV debe existir y ser > 0
    - EV/Revenue <= 40x (Palantir es ~30x, más que eso es outlier)
    - EV/EBITDA <= 75x (growth companies pueden tener 50-60x, más es ruido)
    - Gross Margin <= 100% (imposible por definición)
    - Net Margin no puede ser > 500% (señal de moneda local sin convertir)
    - Revenue no puede ser > 2,000,000 mm (señal de moneda local)
    """
    if not data:
        return None
    
    ticker = data.get("Ticker", "???")
    rev = data.get("Revenue ($mm)")
    ev = data.get("EV ($mm)")
    ebitda = data.get("EBITDA ($mm)")
    
    # Sin revenue = inútil
    if not rev or rev <= 0:
        return None
    
    # Revenue absurdamente alto = moneda local no convertida
    if rev > 2_000_000:
        logger.warning(f"[{ticker}] DESCARTADO: Revenue ${rev:,.0f}mm parece moneda local")
        return None
    
    # EV negativo o inexistente
    if not ev or ev <= 0:
        logger.warning(f"[{ticker}] DESCARTADO: EV negativo o inexistente ({ev})")
        return None
    
    # EV/Revenue > 40x
    ev_rev = ev / rev
    if ev_rev > 40:
        logger.warning(f"[{ticker}] DESCARTADO: EV/Revenue {ev_rev:.1f}x > 40x")
        return None
    
    # EV/EBITDA > 75x (solo si EBITDA existe y es positivo)
    if ebitda and ebitda > 0:
        ev_ebitda = ev / ebitda
        if ev_ebitda > 75:
            logger.warning(f"[{ticker}] DESCARTADO: EV/EBITDA {ev_ebitda:.1f}x > 75x")
            return None
    
    # EBITDA negativo — no sirve para valuation por múltiplos
    if ebitda is not None and ebitda < 0:
        logger.warning(f"[{ticker}] DESCARTADO: EBITDA negativo ({ebitda})")
        return None
    
    # Gross Margin > 100% = imposible
    gross = data.get("Gross ($mm)")
    if gross and rev and rev > 0:
        gross_mg = gross / rev * 100
        if gross_mg > 100:
            logger.warning(f"[{ticker}] DESCARTADO: Gross Margin {gross_mg:.1f}% > 100%")
            return None
    
    # Net Margin > 500% = claramente datos corruptos
    net = data.get("Net Inc ($mm)")
    if net and rev and rev > 0:
        net_mg = abs(net) / rev * 100
        if net_mg > 500:
            logger.warning(f"[{ticker}] DESCARTADO: Net Margin {net_mg:.1f}% > 500% (datos corruptos)")
            return None
    
    return data


# ─────────────────────────────────────────────
# 3. TTM FETCH — CON FX FIX
# ─────────────────────────────────────────────

def get_financials_ttm(ticker: str) -> Optional[dict]:
    """
    Extrae datos financieros con TTM REAL.
    v6: FX conversion corregida — se ejecuta DESPUÉS de definir todas las variables.
    """
    # ── CHECK CACHE ──
    cached = _cache_get(ticker)
    if cached is not None:
        logger.info(f"[{ticker}] CACHE HIT")
        return cached if cached != "__NONE__" else None

    # ── FETCH DESDE YAHOO ──
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        if not info or info.get("quoteType") not in ("EQUITY",):
            _cache_set(ticker, "__NONE__")
            return None

        def mm(val):
            if val is None or pd.isna(val):
                return None
            try:
                return round(float(val) / 1_000_000, 1)
            except (TypeError, ValueError):
                return None

        # ── IDENTIFICACIÓN ──
        empresa = info.get("shortName", ticker)
        pais = info.get("country", "N/A")
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        desc = info.get("longBusinessSummary", "")
        if desc and len(desc) > 300:
            truncated = desc[:300]
            last_period = truncated.rfind('. ')
            if last_period > 100:
                desc = truncated[:last_period + 1]
            else:
                last_space = truncated.rfind(' ')
                desc = truncated[:last_space] + "…" if last_space > 100 else truncated + "…"

        # ── TTM REVENUE & EBITDA ──
        ttm_method = "quarterly"
        quarters_used = 0
        revenue_ttm_raw = None
        ebitda_ttm_raw = None

        try:
            qf = t.quarterly_financials
            if qf is not None and not qf.empty:
                for key in ["Total Revenue", "Revenue", "Net Revenue", "Operating Revenue"]:
                    if key in qf.index:
                        row = qf.loc[key]
                        quarters_used = _quarters_available(row)
                        if quarters_used >= 4:
                            revenue_ttm_raw = _sum_last_4q(row)
                            break

                for key in ["EBITDA", "Normalized EBITDA"]:
                    if key in qf.index:
                        row = qf.loc[key]
                        if _quarters_available(row) >= 4:
                            ebitda_ttm_raw = _sum_last_4q(row)
                            break

                if ebitda_ttm_raw is None:
                    ebit_row = da_row = None
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

        # ── FALLBACK ──
        if revenue_ttm_raw is None:
            revenue_ttm_raw = info.get("totalRevenue")
            ttm_method = "info_fallback"
            quarters_used = 0

        if ebitda_ttm_raw is None:
            ebitda_ttm_raw = info.get("ebitda")

        revenue_mm = mm(revenue_ttm_raw)
        ebitda_mm = mm(ebitda_ttm_raw)

        if not revenue_mm:
            _cache_set(ticker, "__NONE__")
            return None

        # ── BALANCE SHEET (definir TODO antes de FX conversion) ──
        net_income_mm = mm(info.get("netIncomeToCommon"))
        gross_mm = mm(info.get("grossProfits"))
        total_debt_mm = mm(info.get("totalDebt"))
        cash_mm = mm(info.get("totalCash"))
        mkt_cap_mm = mm(info.get("marketCap"))
        ev_mm = mm(info.get("enterpriseValue"))

        # ── FX CONVERSION (DESPUÉS de definir todas las variables) ──
        fin_currency = info.get("financialCurrency", "USD")
        if fin_currency and fin_currency != "USD":
            try:
                fx_ticker = f"{fin_currency}USD=X"
                fx_rate = yf.Ticker(fx_ticker).info.get("regularMarketPrice")
                if fx_rate and fx_rate > 0:
                    if revenue_mm:    revenue_mm = round(revenue_mm * fx_rate, 1)
                    if ebitda_mm:     ebitda_mm = round(ebitda_mm * fx_rate, 1)
                    if net_income_mm: net_income_mm = round(net_income_mm * fx_rate, 1)
                    if gross_mm:      gross_mm = round(gross_mm * fx_rate, 1)
                    if total_debt_mm: total_debt_mm = round(total_debt_mm * fx_rate, 1)
                    if cash_mm:       cash_mm = round(cash_mm * fx_rate, 1)
                    # EV y Mkt Cap ya están en USD en yfinance (marketCap siempre es USD)
                    # NO convertir ev_mm ni mkt_cap_mm
                    logger.info(f"[{ticker}] Converted from {fin_currency} → USD (rate={fx_rate})")
            except Exception as e:
                logger.warning(f"[{ticker}] FX conversion failed: {e}")

        # ── MÚLTIPLOS ──
        ev_revenue = _safe_round(ev_mm / revenue_mm, 1) if ev_mm and revenue_mm and revenue_mm > 0 else None
        ev_ebitda = _safe_round(ev_mm / ebitda_mm, 1) if ev_mm and ebitda_mm and ebitda_mm > 0 else None
        pe = _safe_round(info["trailingPE"], 1) if info.get("trailingPE") else None

        # ── MÁRGENES ──
        ebitda_margin = _safe_round(ebitda_mm / revenue_mm * 100, 1) if ebitda_mm and revenue_mm and revenue_mm > 0 else None
        net_margin = _safe_round(net_income_mm / revenue_mm * 100, 1) if net_income_mm and revenue_mm and revenue_mm > 0 else None
        gross_margin = _safe_round(gross_mm / revenue_mm * 100, 1) if gross_mm and revenue_mm and revenue_mm > 0 else None

        # ── GROWTH ──
        rev_growth = _safe_round(info["revenueGrowth"] * 100, 1) if info.get("revenueGrowth") is not None else None

        result = {
            "Ticker": ticker,
            "Empresa": empresa,
            "Pais": pais,  # ← CORREGIDO: con acento (antes era "Pais")
            "Sector": sector,
            "Industria": industry,
            "Descripción": desc,
            "Revenue ($mm)": revenue_mm,
            "EBITDA ($mm)": ebitda_mm,
            "Net Inc ($mm)": net_income_mm,
            "Gross ($mm)": gross_mm,
            "Deuda ($mm)": total_debt_mm,
            "Cash ($mm)": cash_mm,
            "Mkt Cap ($mm)": mkt_cap_mm,
            "EV ($mm)": ev_mm,
            "EV/Revenue": ev_revenue,
            "EV/EBITDA": ev_ebitda,
            "P/E": pe,
            "EBITDA Mg%": ebitda_margin,
            "Net Mg%": net_margin,
            "Gross Mg%": gross_margin,
            "Rev Growth %": rev_growth,
            "Empleados": info.get("fullTimeEmployees"),
            "Currency": fin_currency,
            "ttm_method": ttm_method,
            "quarters_used": quarters_used,
        }

        # ── SANITIZE: descartar si los datos no pasan validación ──
        result = sanitize_empresa(result)
        if result is None:
            _cache_set(ticker, "__NONE__")
            return None

        _cache_set(ticker, result)
        return result

    except Exception as e:
        logger.warning(f"[{ticker}] get_financials_ttm failed: {e}")
        _cache_set(ticker, "__NONE__")
        return None


# ─────────────────────────────────────────────
# 4. PARALLEL FETCH
# ─────────────────────────────────────────────

def fetch_many_parallel(tickers: list[str], max_workers: int = 10) -> list[dict]:
    """
    Baja datos de múltiples tickers EN PARALELO.
    Cada resultado ya pasa por sanitize_empresa() automáticamente.
    """
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {
            executor.submit(get_financials_ttm, ticker): ticker
            for ticker in tickers
        }

        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                data = future.result(timeout=15)
                if data is not None:
                    results.append(data)
            except Exception as e:
                logger.warning(f"[{ticker}] parallel fetch failed: {e}")

    return results


# ─────────────────────────────────────────────
# 5. STATS LAYER
# ─────────────────────────────────────────────

def calculate_comps_stats(empresas: list[dict]) -> dict:
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
            "mean": _safe_round(series.mean(), 2),
            "median": _safe_round(series.median(), 2),
            "min": _safe_round(series.min(), 2),
            "max": _safe_round(series.max(), 2),
            "count": int(len(series)),
        }

    return {"n_empresas": len(empresas), "metrics": stats}


# ─────────────────────────────────────────────
# 6. NaN CLEANER
# ─────────────────────────────────────────────

def _clean_nan(obj):
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(item) for item in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


# ─────────────────────────────────────────────
# 7. COMPS RESPONSE BUILDER
# ─────────────────────────────────────────────

def build_comps_response(
    empresas: list[dict],
    empresa_target: str,
    sector: str,
    revenue_target: float,
    rango_min_pct: float = 0.3,
    rango_max_pct: float = 3.0,
) -> dict:
    empresas = _clean_nan(empresas)

    stats = calculate_comps_stats(empresas)

    n_quarterly = sum(1 for e in empresas if e.get("ttm_method") == "quarterly")
    n_fallback = sum(1 for e in empresas if e.get("ttm_method") == "info_fallback")

    ttm_quality = {
        "quarterly_ttm": n_quarterly,
        "info_fallback": n_fallback,
        "pct_real_ttm": round(n_quarterly / len(empresas) * 100, 1) if empresas else 0,
    }

    return _clean_nan({
        "empresa_target": empresa_target,
        "sector": sector,
        "revenue_target": revenue_target,
        "n_empresas_universe": len(empresas),
        "n_empresas_filtradas": len(empresas),
        "ttm_quality": ttm_quality,
        "stats_universe": stats,
        "stats_filtradas": stats,
        "empresas_filtradas": empresas,
        "empresas_universe": empresas,
    })