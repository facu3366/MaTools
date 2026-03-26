"""
🧠 AI COMP VALIDATOR — DealDesk
================================
Filtro inteligente de comparables usando Claude Haiku.

PROBLEMA: Yahoo Finance clasifica Tesla como "Consumer Cyclical" junto con Walmart.
          Los mappings estáticos (INDUSTRY_GROUPS) nunca cubren todos los edge cases.

SOLUCIÓN: Después de juntar candidatos, la IA evalúa cuáles son comparables REALES
          basándose en modelo de negocio, no en clasificación de sector.

COSTO: ~$0.001 por request con Haiku. 1000 análisis = $1.

FALLBACK: Si la API falla, devuelve todos los candidatos sin filtrar.
          La demo NUNCA se cae por culpa de este módulo.

USO:
    from Backend.modules.ai_filter import ai_filter_comps
    
    filtered = await ai_filter_comps(
        target_ticker="TSLA",
        target_name="Tesla",
        target_industry="Auto Manufacturers",
        candidates=list_of_dicts,
    )
"""

import os
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

MODEL = "claude-haiku-4-5-20251001"  # Cheapest, fastest — perfect for classification
MAX_CANDIDATES_TO_SEND = 40          # Don't send 80 companies to the AI — waste of tokens
MAX_TOKENS_RESPONSE = 1500
TIMEOUT_SECONDS = 12                 # If Haiku doesn't answer in 12s, skip AI filter

# ─────────────────────────────────────────────
# PROMPT TEMPLATE
# ─────────────────────────────────────────────

FILTER_PROMPT = """You are a senior M&A analyst. Your job is to filter a list of candidate comparable companies.

TARGET COMPANY:
- Ticker: {target_ticker}
- Name: {target_name}
- Industry: {target_industry}
- Revenue: ${target_revenue:,.0f}M USD

CANDIDATE COMPANIES:
{candidates_text}

TASK: Return ONLY the tickers that are legitimate comparable companies for an M&A valuation.

RULES:
1. Comparable = similar BUSINESS MODEL, not just same sector classification
2. A car manufacturer is NOT comparable to a supermarket even if both are "Consumer"
3. A health insurer is NOT comparable to a pharma company even if both are "Healthcare"
4. Revenue scale matters: a $500M company is not a good comp for a $200B company (unless no alternatives)
5. Keep at least 5 comps, maximum 25
6. When in doubt, INCLUDE the company (false negatives are worse than false positives)

Return ONLY a JSON array of ticker strings. No explanation, no markdown, no backticks.
Example: ["AAPL","MSFT","GOOGL"]
"""


def _build_candidates_text(candidates: list[dict]) -> str:
    """Build a compact text representation of candidates for the prompt."""
    lines = []
    for c in candidates[:MAX_CANDIDATES_TO_SEND]:
        ticker = c.get("Ticker", "???")
        name = c.get("Empresa", ticker)
        industry = c.get("Industria", "N/A")
        rev = c.get("Revenue ($mm)", 0) or 0
        country = c.get("País") or c.get("Pais") or "N/A"
        lines.append(f"- {ticker}: {name} | Industry: {industry} | Rev: ${rev:,.0f}M | {country}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# SYNC VERSION (for current FastAPI sync endpoints)
# ─────────────────────────────────────────────

def ai_filter_comps(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    candidates: list[dict],
) -> list[dict]:
    """
    Filters candidate comps using Claude Haiku.
    
    Returns filtered list. If AI fails for ANY reason, returns original list.
    This function NEVER raises exceptions — graceful degradation always.
    
    Args:
        target_ticker: e.g. "TSLA"
        target_name: e.g. "Tesla, Inc."  
        target_industry: e.g. "Auto Manufacturers"
        target_revenue: in $mm USD
        candidates: list of dicts from fetch_many_parallel()
    
    Returns:
        Filtered list of candidate dicts
    """
    # ── GUARD CLAUSES ──
    if not ANTHROPIC_KEY:
        logger.warning("[AI Filter] No ANTHROPIC_API_KEY — skipping AI filter")
        return candidates
    
    if len(candidates) <= 5:
        logger.info(f"[AI Filter] Only {len(candidates)} candidates — no filtering needed")
        return candidates
    
    if not target_industry:
        logger.warning("[AI Filter] No target industry — skipping AI filter")
        return candidates

    # ── BUILD PROMPT ──
    candidates_text = _build_candidates_text(candidates)
    
    prompt = FILTER_PROMPT.format(
        target_ticker=target_ticker,
        target_name=target_name,
        target_industry=target_industry,
        target_revenue=target_revenue or 0,
        candidates_text=candidates_text,
    )

    # ── CALL HAIKU ──
    try:
        import anthropic
        
        t0 = time.time()
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_RESPONSE,
            messages=[{"role": "user", "content": prompt}],
            timeout=TIMEOUT_SECONDS,
        )
        
        elapsed = time.time() - t0
        raw_text = response.content[0].text.strip()
        
        # ── PARSE RESPONSE ──
        # Clean up common LLM formatting issues
        clean = raw_text
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1]  # remove first line
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()
        
        approved_tickers = json.loads(clean)
        
        if not isinstance(approved_tickers, list):
            logger.warning(f"[AI Filter] Response is not a list: {type(approved_tickers)}")
            return candidates
        
        approved_set = set(t.upper() for t in approved_tickers if isinstance(t, str))
        
        # ── FILTER ──
        filtered = [c for c in candidates if c.get("Ticker", "").upper() in approved_set]
        
        removed = len(candidates) - len(filtered)
        
        logger.info(
            f"[AI Filter] {target_ticker} | {len(candidates)} candidates → "
            f"{len(filtered)} approved, {removed} removed | "
            f"{elapsed:.1f}s | model={MODEL}"
        )
        
        # ── SANITY CHECK ──
        # If AI removed too many (left < 5), something went wrong — return all
        if len(filtered) < 5 and len(candidates) >= 5:
            logger.warning(
                f"[AI Filter] Only {len(filtered)} left after filter (had {len(candidates)}). "
                f"Falling back to unfiltered list."
            )
            return candidates
        
        # Log what got removed for debugging
        if removed > 0:
            removed_tickers = [
                c.get("Ticker") for c in candidates 
                if c.get("Ticker", "").upper() not in approved_set
            ]
            logger.info(f"[AI Filter] Removed: {removed_tickers[:10]}{'...' if len(removed_tickers) > 10 else ''}")
        
        return filtered
        
    except json.JSONDecodeError as e:
        logger.warning(f"[AI Filter] JSON parse error: {e}. Raw: {raw_text[:200]}")
        return candidates
    
    except Exception as e:
        logger.warning(f"[AI Filter] Failed ({type(e).__name__}: {e}). Using unfiltered list.")
        return candidates


# ─────────────────────────────────────────────
# CACHE (optional — avoid re-filtering same target)
# ─────────────────────────────────────────────

_ai_filter_cache = {}

def ai_filter_comps_cached(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    candidates: list[dict],
) -> list[dict]:
    """
    Same as ai_filter_comps but with a simple in-memory cache.
    Cache key = (target_ticker, frozenset of candidate tickers).
    """
    candidate_key = frozenset(c.get("Ticker", "") for c in candidates)
    cache_key = (target_ticker, candidate_key)
    
    if cache_key in _ai_filter_cache:
        cached_tickers = _ai_filter_cache[cache_key]
        filtered = [c for c in candidates if c.get("Ticker") in cached_tickers]
        logger.info(f"[AI Filter] CACHE HIT for {target_ticker}: {len(filtered)} comps")
        return filtered
    
    result = ai_filter_comps(
        target_ticker, target_name, target_industry, target_revenue, candidates
    )
    
    # Store approved tickers in cache
    _ai_filter_cache[cache_key] = set(c.get("Ticker") for c in result)
    
    return result