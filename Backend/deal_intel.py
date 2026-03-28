"""
🧠 DEAL INTELLIGENCE — DealDesk
=================================
Genera un mini-brief de M&A para cada empresa comparable.
Para cada comp: por qué es buen/mal target, sinergias, riesgos,
si está en expansión, y una recomendación de approach.

Se ejecuta DESPUÉS de tener los comps — no bloquea la tabla principal.
Se llama como endpoint separado para no ralentizar la carga inicial.
"""

import os
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import google.generativeai as genai

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

router = APIRouter()


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class DealIntelRequest(BaseModel):
    target_ticker: str
    target_name: str
    target_industry: str
    target_revenue: float  # in $mm
    comps: list[dict]      # list of comp empresas with financial data


# ─────────────────────────────────────────────
# GEMINI
# ─────────────────────────────────────────────

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
try:
    model = genai.GenerativeModel("gemini-2.0-flash")
    GEMINI_OK = True
except Exception as e:
    print(f"⚠️ Gemini init failed: {e}")
    model = None
    GEMINI_OK = False


def _call_ai(prompt: str) -> str | None:
    if not model:
        return None

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 300,
            },
        )
        return response.text if response else None

    except Exception as e:
        print(f"❌ Gemini failed: {e}")
        return None


# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────

import re


def generate_deal_intelligence(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    comps: list[dict],
) -> list[dict]:

    print("\n" + "=" * 60)
    print("🧠 DEAL INTEL START")
    print(f"Target: {target_name} ({target_ticker})")
    print(f"Comps received: {len(comps)}")
    print("=" * 60)

    if not model:
        print("❌ Gemini model NOT available")
        return []

    if not comps:
        print("⚠️ No comps provided")
        return []

    # ─────────────────────────────
    # PRINT MODELOS DISPONIBLES
    # ─────────────────────────────
    try:
        print("\n📦 AVAILABLE MODELS:")
        for m in genai.list_models():
            print(" -", m.name)
    except Exception as e:
        print("⚠️ Could not list models:", e)

    # ─────────────────────────────
    # EXCLUSION LIST
    # ─────────────────────────────
    tier1 = set()

    if target_ticker:
        tier1.add(target_ticker.upper())

    for c in comps:
        t = str(c.get("Ticker") or c.get("ticker") or "").upper()
        if t:
            tier1.add(t)

    tier1_list = list(tier1)
    tier1_text = ", ".join(tier1_list[:15])

    print(f"\n🚫 Excluded tickers: {tier1_text}")

    # ─────────────────────────────
    # PROMPT SIMPLE
    # ─────────────────────────────
    prompt = f"""
Return a JSON array of 3 companies.

Target: {target_name} ({target_ticker})
Industry: {target_industry}

DO NOT include these tickers:
{tier1_text}

Each object:
{{
  "ticker": "...",
  "tier": "TIER_2" or "TIER_3",
  "deal_thesis": "short explanation"
}}

Rules:
- No markdown
- No explanations
- Keep it short
"""

    print("\n🧾 PROMPT SIZE:", len(prompt))

    # ─────────────────────────────
    # CALL AI
    # ─────────────────────────────
    raw = _call_ai(prompt)

    print("\n🧠 RAW LENGTH:", len(raw) if raw else 0)

    if not raw:
        print("❌ EMPTY RESPONSE → fallback")
        raw = ""

    print("\n🧠 RAW PREVIEW:")
    print(raw[:300])
    print("—" * 40)

    # ─────────────────────────────
    # PARSER SIMPLE
    # ─────────────────────────────
    clean = raw.strip().replace("```json", "").replace("```", "")

    matches = re.findall(r"\{.*?\}", clean, re.DOTALL)

    print(f"\n🔍 OBJECTS FOUND: {len(matches)}")

    results = []

    for m in matches:
        try:
            obj = json.loads(m)

            ticker = str(obj.get("ticker", "")).upper().strip()

            if not ticker or ticker in tier1:
                continue

            results.append({
                "ticker": ticker,
                "tier": obj.get("tier", ""),
                "deal_thesis": obj.get("deal_thesis", ""),
            })

        except Exception:
            continue

    # ─────────────────────────────
    # FALLBACK SIMPLE
    # ─────────────────────────────
    if not results:
        print("⚠️ Using fallback")

        for c in comps:
            t = str(c.get("Ticker") or c.get("ticker") or "").upper()

            if not t or t == target_ticker or t in tier1:
                continue

            results.append({
                "ticker": t,
                "tier": "TIER_2",
                "deal_thesis": "Potential strategic fit based on industry adjacency.",
            })

            if len(results) >= 3:
                break

    print(f"\n🧠 FINAL OUTPUT ({len(results)}):\n{results}")
    print("=" * 60 + "\n")

    return results[:3]


# ─────────────────────────────────────────────
# API ENDPOINT
# ─────────────────────────────────────────────

@router.post("/comps/deal-intel")
def get_deal_intelligence(request: DealIntelRequest):
    """
    Generate deal intelligence for comps.
    Called AFTER comps are loaded — doesn't block the main table.
    """
    if not ANTHROPIC_KEY:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")

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