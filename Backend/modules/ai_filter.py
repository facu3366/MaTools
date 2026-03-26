"""
🧠 AI COMP VALIDATOR — DealDesk
================================
Filtro inteligente de comparables usando Claude Sonnet.
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

MODELS_TO_TRY = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
    "claude-3-5-haiku-20241022",
    "claude-3-haiku-20240307",
]

MAX_CANDIDATES_TO_SEND = 40
MAX_TOKENS_RESPONSE = 1500
TIMEOUT_SECONDS = 20

# ─────────────────────────────────────────────
# PROMPT TEMPLATE
# ─────────────────────────────────────────────

FILTER_PROMPT = """You are the top-ranked Associate at Goldman Sachs M&A. Your Managing Director just handed you a list of candidate comparable companies for a live deal. If you include a bad comp, the MD will destroy you in front of the entire team. If you miss a good comp, you're equally dead. Your reputation depends on this.

TARGET COMPANY:
- Ticker: {target_ticker}
- Name: {target_name}
- Industry: {target_industry}
- Revenue: ${target_revenue:,.0f}M USD

CANDIDATE COMPANIES:
{candidates_text}

YOUR TASK: Filter ruthlessly. Return ONLY legitimate comparable companies.

THE MD'S RULES (non-negotiable):
1. SAME CORE BUSINESS — the company must make money the same way the target does. Same products, same customers, same value chain position.
2. If the target MANUFACTURES CARS → only include companies that MANUFACTURE cars or vehicles. Not retailers. Not food. Not aerospace. Not auto parts stores.
3. If the target SELLS SOFTWARE → only include software companies. Not hardware. Not IT consulting. Not telecom.
4. If the target is a HEALTH INSURER → only include health insurers and managed care. Not pharma. Not medical devices. Not hospitals.
5. If the target is an E-COMMERCE PLATFORM → only include e-commerce and digital marketplace companies. Not brick-and-mortar retail.
6. If the target is a BANK → only include banks. Not insurance. Not asset managers. Not payment processors.
7. REJECT companies from different industries even if Yahoo Finance classifies them in the same sector. Coca-Cola is NOT a comp for Tesla. Boeing is NOT a comp for Toyota. Walmart is NOT a comp for Ford. Home Depot is NOT a comp for GM.
8. Auto parts RETAILERS (AutoZone, O'Reilly) are NOT comparable to auto MANUFACTURERS.
9. Defense contractors (Lockheed, RTX, Northrop) are NOT comparable to auto manufacturers.
10. Consumer staples (P&G, Coca-Cola, PepsiCo) are NOT comparable to auto manufacturers or tech companies.
11. Revenue scale: prefer companies within 0.2x-5x of target revenue, but include smaller/larger if business model is identical and no alternatives exist.
12. Return between 8 and 20 comps. Quality over quantity. Every ticker you return must be defensible to the MD.

Return ONLY a JSON array of ticker strings. No explanation. No markdown. No backticks. Just the array.
Example: ["TM","GM","F","STLA","HMC"]"""


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
# CALL AI WITH MODEL FALLBACK
# ─────────────────────────────────────────────

def _call_ai(prompt: str) -> Optional[str]:
    """Try multiple model strings until one works. Returns raw text or None."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    for model in MODELS_TO_TRY:
        try:
            print(f"   🧠 [AI Filter] Trying model: {model}")
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS_RESPONSE,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            print(f"   🧠 [AI Filter] SUCCESS with {model} — response length: {len(raw)}")
            return raw
        except Exception as e:
            print(f"   ⚠️ [AI Filter] Model {model} failed: {type(e).__name__}: {e}")
            continue

    return None


# ─────────────────────────────────────────────
# MAIN FILTER FUNCTION
# ─────────────────────────────────────────────

def ai_filter_comps(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    candidates: list[dict],
) -> list[dict]:
    """
    Filters candidate comps using Claude.
    NEVER raises exceptions — graceful degradation always.
    """
    if not ANTHROPIC_KEY:
        print("   ⚠️ [AI Filter] No ANTHROPIC_API_KEY — skipping")
        return candidates

    if len(candidates) <= 5:
        print(f"   🧠 [AI Filter] Only {len(candidates)} candidates — no filtering needed")
        return candidates

    if not target_industry:
        print("   ⚠️ [AI Filter] No target industry — skipping")
        return candidates

    print(f"   🧠 [AI Filter] Starting: {target_ticker} ({target_name}) | {target_industry} | {len(candidates)} candidates")

    candidates_text = _build_candidates_text(candidates)

    prompt = FILTER_PROMPT.format(
        target_ticker=target_ticker,
        target_name=target_name,
        target_industry=target_industry,
        target_revenue=target_revenue or 0,
        candidates_text=candidates_text,
    )

    try:
        t0 = time.time()
        raw_text = _call_ai(prompt)
        elapsed = time.time() - t0

        if raw_text is None:
            print(f"   ⚠️ [AI Filter] All models failed. Using unfiltered list.")
            return candidates

        clean = raw_text
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()

        start_idx = clean.find("[")
        end_idx = clean.rfind("]")
        if start_idx != -1 and end_idx != -1:
            clean = clean[start_idx:end_idx + 1]

        approved_tickers = json.loads(clean)

        if not isinstance(approved_tickers, list):
            print(f"   ⚠️ [AI Filter] Response is not a list: {type(approved_tickers)}")
            return candidates

        approved_set = set(t.upper() for t in approved_tickers if isinstance(t, str))

        filtered = [c for c in candidates if c.get("Ticker", "").upper() in approved_set]
        removed = len(candidates) - len(filtered)

        print(f"   🧠 [AI Filter] RESULT: {len(candidates)} → {len(filtered)} approved, {removed} removed | {elapsed:.1f}s")

        if removed > 0:
            removed_tickers = [c.get("Ticker") for c in candidates if c.get("Ticker", "").upper() not in approved_set]
            print(f"   🧠 [AI Filter] Removed: {removed_tickers[:20]}")

        if len(filtered) < 5 and len(candidates) >= 5:
            print(f"   ⚠️ [AI Filter] Only {len(filtered)} left — falling back to unfiltered")
            return candidates

        return filtered

    except json.JSONDecodeError as e:
        print(f"   ⚠️ [AI Filter] JSON parse error: {e}. Raw: {raw_text[:300] if raw_text else 'None'}")
        return candidates

    except Exception as e:
        print(f"   ⚠️ [AI Filter] Failed ({type(e).__name__}: {e}). Using unfiltered list.")
        return candidates


# ─────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────

_ai_filter_cache = {}

def ai_filter_comps_cached(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    candidates: list[dict],
) -> list[dict]:
    candidate_key = frozenset(c.get("Ticker", "") for c in candidates)
    cache_key = (target_ticker, candidate_key)

    if cache_key in _ai_filter_cache:
        cached_tickers = _ai_filter_cache[cache_key]
        filtered = [c for c in candidates if c.get("Ticker") in cached_tickers]
        print(f"   🧠 [AI Filter] CACHE HIT for {target_ticker}: {len(filtered)} comps")
        return filtered

    result = ai_filter_comps(
        target_ticker, target_name, target_industry, target_revenue, candidates
    )

    _ai_filter_cache[cache_key] = set(c.get("Ticker") for c in result)

    return result