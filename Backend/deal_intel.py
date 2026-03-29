"""
🧠 DEAL INTELLIGENCE — DealDesk
=================================
Genera un mini-brief de M&A para cada empresa comparable.
Usa Google Gemini 1.5 Flash (gratis) para generar briefs.
"""

import os
import json
import logging
import time
import requests
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAnBovaLp2o8B45ytc59NcrEnU48vnsfz8")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

router = APIRouter()

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class DealIntelRequest(BaseModel):
    target_ticker: str
    target_name: str
    target_industry: str
    target_revenue: float
    comps: list[dict]


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

DEAL_INTEL_PROMPT = """You are the #1 ranked M&A analyst at Goldman Sachs. Your MD needs deal intelligence on potential acquirers/targets for a live mandate.

TARGET COMPANY (the company being sold):
- Name: {target_name} ({target_ticker})
- Industry: {target_industry}
- Revenue: ${target_revenue:,.0f}M USD

COMPARABLE COMPANIES TO ANALYZE:
{comps_text}

For EACH company above, provide a JSON object with these EXACT fields:
- "ticker": the company ticker
- "tier": one of "STRATEGIC_BUYER", "FINANCIAL_SPONSOR", "ADJACENT_SYNERGY"
- "deal_thesis": 2-3 sentences on WHY this company would acquire the target. Be specific.
- "risks": 1-2 specific risks of this acquirer
- "expansion_signal": "HIGH", "MEDIUM", or "LOW"
- "expansion_note": 1 sentence explaining the expansion signal
- "approach_rec": "PRIORITY", "SECONDARY", or "MONITOR"

Return ONLY a JSON array. No explanation. No markdown. No backticks.
Example: [{{"ticker":"TM","tier":"STRATEGIC_BUYER","deal_thesis":"...","risks":"...","expansion_signal":"MEDIUM","expansion_note":"...","approach_rec":"PRIORITY"}}]"""


def _build_comps_text(comps: list[dict]) -> str:
    lines = []
    for c in comps[:20]:
        ticker = c.get("Ticker") or c.get("ticker") or "???"
        name = c.get("Empresa") or c.get("name") or ticker
        industry = c.get("Industria") or c.get("industry") or "N/A"
        rev = c.get("Revenue ($mm)") or c.get("revenue") or 0
        ebitda = c.get("EBITDA ($mm)") or c.get("ebitda") or 0
        ev = c.get("EV ($mm)") or c.get("ev") or 0
        country = c.get("País") or c.get("Pais") or c.get("country") or "N/A"

        lines.append(
            f"- {ticker}: {name} | {industry} | {country} | "
            f"Rev: ${rev:,.0f}M | EBITDA: ${ebitda:,.0f}M | EV: ${ev:,.0f}M"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────
# CALL GEMINI
# ─────────────────────────────────────────────

def _call_gemini(prompt: str) -> str | None:
    if not GEMINI_KEY:
        print("   ⚠️ No GEMINI_API_KEY")
        return None

    try:
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 2048,
                }
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(f"   ❌ Gemini HTTP {response.status_code}: {response.text[:200]}")
            return None

        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        print(f"   ✅ Gemini response: {len(text)} chars")
        return text

    except Exception as e:
        print(f"   ❌ Gemini error: {e}")
        return None


# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────

def generate_deal_intelligence(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    comps: list[dict],
) -> list[dict]:
    if not GEMINI_KEY:
        print("   ⚠️ [Deal Intel] No GEMINI_API_KEY — skipping")
        return []

    if not comps:
        return []

    print(f"   🧠 [Deal Intel] Generating briefs for {len(comps)} companies via Gemini...")

    comps_text = _build_comps_text(comps)
    prompt = DEAL_INTEL_PROMPT.format(
        target_name=target_name,
        target_ticker=target_ticker,
        target_industry=target_industry,
        target_revenue=target_revenue or 0,
        comps_text=comps_text,
    )

    try:
        t0 = time.time()
        raw_text = _call_gemini(prompt)
        elapsed = time.time() - t0

        if raw_text is None:
            return []

        # Clean response
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

        briefs = json.loads(clean)

        if not isinstance(briefs, list):
            print(f"   ⚠️ [Deal Intel] Response is not a list")
            return []

        # Map briefs back to tickers
        brief_map = {b.get("ticker", "").upper(): b for b in briefs}

        result = []
        for comp in comps:
            ticker = (comp.get("Ticker") or comp.get("ticker") or "").upper()
            brief = brief_map.get(ticker, {})
            result.append({
                "ticker": ticker,
                "tier": brief.get("tier", "STRATEGIC_BUYER"),
                "deal_thesis": brief.get("deal_thesis", ""),
                "risks": brief.get("risks", ""),
                "expansion_signal": brief.get("expansion_signal", "MEDIUM"),
                "expansion_note": brief.get("expansion_note", ""),
                "approach_rec": brief.get("approach_rec", "SECONDARY"),
            })

        print(f"   🧠 [Deal Intel] Generated {len(result)} briefs in {elapsed:.1f}s")
        return result

    except json.JSONDecodeError as e:
        print(f"   ⚠️ [Deal Intel] JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"   ⚠️ [Deal Intel] Failed: {type(e).__name__}: {e}")
        return []


# ─────────────────────────────────────────────
# API ENDPOINT
# ─────────────────────────────────────────────

@router.post("/comps/deal-intel")
def get_deal_intelligence(request: DealIntelRequest):
    if not GEMINI_KEY:
        raise HTTPException(503, "GEMINI_API_KEY not configured")

    briefs = generate_deal_intelligence(
        target_ticker=request.target_ticker,
        target_name=request.target_name,
        target_industry=request.target_industry,
        target_revenue=request.target_revenue,
        comps=request.comps,
    )

    return {
        "target": request.target_ticker,
        "n_briefs": len(briefs),
        "briefs": briefs,
    }