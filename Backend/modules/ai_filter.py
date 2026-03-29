"""
🧠 AI COMP VALIDATOR — DealDesk
================================
Filtro inteligente de comparables usando Google Gemini 1.5 Flash.
"""

import os
import json
import logging
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnBovaLp2o8B45ytc59NcrEnU48vnsfz8")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

MAX_CANDIDATES_TO_SEND = 40

# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

FILTER_PROMPT = """You are the top-ranked Associate at Goldman Sachs M&A. Filter candidate comparable companies ruthlessly.

TARGET COMPANY:
- Ticker: {target_ticker}
- Name: {target_name}
- Industry: {target_industry}
- Revenue: ${target_revenue:,.0f}M USD

CANDIDATE COMPANIES:
{candidates_text}

RULES:
1. SAME CORE BUSINESS only — the company must make money the same way the target does.
2. REJECT companies from different industries even if Yahoo classifies them in the same sector.
3. Auto parts RETAILERS are NOT comparable to auto MANUFACTURERS.
4. Defense contractors are NOT comparable to auto manufacturers.
5. Consumer staples are NOT comparable to tech companies.
6. Return between 8 and 20 comps. Quality over quantity.

Return ONLY a JSON array of ticker strings. No explanation. No markdown. No backticks.
Example: ["TM","GM","F","STLA","HMC"]"""


def _build_candidates_text(candidates: list[dict]) -> str:
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
# CALL GEMINI
# ─────────────────────────────────────────────

def _call_gemini(prompt: str) -> str | None:
    if not GEMINI_KEY:
        return None

    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1024,
                }
            },
            timeout=20,
        )

        if response.status_code != 200:
            print(f"   ❌ Gemini HTTP {response.status_code}: {response.text[:200]}")
            return None

        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text

    except Exception as e:
        print(f"   ❌ Gemini error: {e}")
        return None


# ─────────────────────────────────────────────
# MAIN FILTER
# ─────────────────────────────────────────────

def ai_filter_comps(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    candidates: list[dict],
) -> list[dict]:
    if not GEMINI_KEY:
        return candidates

    if len(candidates) <= 5:
        return candidates

    if not target_industry:
        return candidates

    print(f"   🧠 [AI Filter] Starting via Gemini: {target_ticker} | {len(candidates)} candidates")

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
        raw_text = _call_gemini(prompt)
        elapsed = time.time() - t0

        if raw_text is None:
            return candidates

        clean = raw_text.strip()
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
            return candidates

        approved_set = set(t.upper() for t in approved_tickers if isinstance(t, str))
        filtered = [c for c in candidates if c.get("Ticker", "").upper() in approved_set]

        print(f"   🧠 [AI Filter] {len(candidates)} → {len(filtered)} approved | {elapsed:.1f}s")

        if len(filtered) < 5 and len(candidates) >= 5:
            return candidates

        return filtered

    except json.JSONDecodeError as e:
        print(f"   ⚠️ [AI Filter] JSON parse error: {e}")
        return candidates
    except Exception as e:
        print(f"   ⚠️ [AI Filter] Failed: {e}")
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
        print(f"   🧠 [AI Filter] CACHE HIT: {len(filtered)} comps")
        return filtered

    result = ai_filter_comps(
        target_ticker, target_name, target_industry, target_revenue, candidates
    )

    _ai_filter_cache[cache_key] = set(c.get("Ticker") for c in result)
    return result