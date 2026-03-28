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
import time
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
# PROMPT
# ─────────────────────────────────────────────

DEAL_INTEL_PROMPT = """You are the #1 ranked M&A analyst at Goldman Sachs. Your MD needs deal intelligence on potential acquirers/targets for a live mandate. Every word you write goes directly into the client pitch book.

TARGET COMPANY (the company being sold):
- Name: {target_name} ({target_ticker})
- Industry: {target_industry}
- Revenue: ${target_revenue:,.0f}M USD

COMPARABLE COMPANIES TO ANALYZE:
{comps_text}

For EACH company above, provide a JSON object with these EXACT fields:
- "ticker": the company ticker
- "tier": one of "STRATEGIC_BUYER", "FINANCIAL_SPONSOR", "ADJACENT_SYNERGY" 
  - STRATEGIC_BUYER = same industry, would buy for market share/consolidation
  - FINANCIAL_SPONSOR = PE-backed or has acquisition history, buys for returns
  - ADJACENT_SYNERGY = different but related business, buys for cross-sell/tech/supply chain
- "deal_thesis": 2-3 sentences on WHY this company would acquire the target. Be specific about synergies (cost savings, revenue, technology, geography). Use real business logic, not generic statements.
- "risks": 1-2 specific risks of this acquirer (regulatory, cultural, financial capacity, strategic fit issues)
- "expansion_signal": "HIGH", "MEDIUM", or "LOW" — is this company actively expanding/acquiring?
- "expansion_note": 1 sentence explaining the expansion signal (recent acquisitions, capex trends, management commentary)
- "approach_rec": "PRIORITY", "SECONDARY", or "MONITOR" — should the deal team contact them now?

CRITICAL RULES:
1. Be brutally honest. If a company is a bad fit, say so.
2. Use the financial data provided — reference specific numbers (revenue scale, margins, growth).
3. STRATEGIC_BUYER is most common (same industry). FINANCIAL_SPONSOR is rare in this list. ADJACENT_SYNERGY is for companies from related but different industries.
4. "approach_rec" = PRIORITY means they have means + motive + fit. SECONDARY means good fit but obstacles. MONITOR means long shot or wait for better timing.

Return ONLY a JSON array. No explanation. No markdown. No backticks.
Example: [{{"ticker":"TM","tier":"STRATEGIC_BUYER","deal_thesis":"...","risks":"...","expansion_signal":"MEDIUM","expansion_note":"...","approach_rec":"PRIORITY"}}]"""


def _build_comps_text(comps: list[dict]) -> str:
    lines = []
    for c in comps[:20]:  # cap at 20 to stay within token limits
        ticker = c.get("Ticker", "???")
        name = c.get("Empresa", ticker)
        industry = c.get("Industria", "N/A")
        rev = c.get("Revenue ($mm)", 0) or 0
        ebitda = c.get("EBITDA ($mm)", 0) or 0
        ev = c.get("EV ($mm)", 0) or 0
        growth = c.get("Rev Growth %", "N/A")
        country = c.get("País") or c.get("Pais") or "N/A"
        ebitda_mg = c.get("EBITDA Mg%", "N/A")
        desc = c.get("Descripción", "")[:150] if c.get("Descripción") else ""
        
        lines.append(
            f"- {ticker}: {name} | {industry} | {country}\n"
            f"  Rev: ${rev:,.0f}M | EBITDA: ${ebitda:,.0f}M ({ebitda_mg}% mg) | EV: ${ev:,.0f}M | Growth: {growth}%\n"
            f"  {desc}"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────
# CALL AI
# ─────────────────────────────────────────────

import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
print("\n📦 MODELOS DISPONIBLES EN TU API KEY:\n")

for m in genai.list_models():
    print(m.name)

print("\n✅ FIN LISTA MODELOS\n")
try:
    model = genai.GenerativeModel("gemini-2.5-flash")
    GEMINI_OK = True
except Exception as e:
    print(f"⚠️ Gemini init failed: {e}")
    model = None
    GEMINI_OK = False
def _call_ai(prompt: str) -> str | None:
    if not model:
        print("⚠️ Gemini not available")
        return None

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 1200,
            },
        )
        return response.text

    except Exception as e:
        print(f"❌ Gemini failed: {e}")
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

    if not model:
        print("   ⚠️ [Deal Intel] Gemini not available")
        return []

    if not comps:
        return []

    print(f"   🧠 [Deal Intel] Generating briefs for {len(comps)} companies...")

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
        raw_text = _call_ai(prompt)
        elapsed = time.time() - t0

        if raw_text is None:
            print("   ⚠️ [Deal Intel] All models failed")
            return []

        # ─────────────────────────────
        # LOG RAW OUTPUT (clave)
        # ─────────────────────────────
        print("\n🧠 RAW AI RESPONSE (first 1000 chars):\n")
        print(raw_text[:1000])
        print("\n🧠 END RAW\n")

        # ─────────────────────────────
        # CLEAN
        # ─────────────────────────────

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

        clean = clean.replace("\n", " ").replace("\r", " ")

        # ─────────────────────────────
        # PARSE
        # ─────────────────────────────

        try:
            briefs = json.loads(clean)

        except json.JSONDecodeError:
            print("   ⚠️ retry JSON parse (regex recovery)...")

            import re

            matches = re.findall(r"\{.*?\}", clean)

            briefs = []
            for m in matches:
                try:
                    obj = json.loads(m)
                    briefs.append(obj)
                except:
                    continue

            if not briefs:
                print("   ⚠️ no valid JSON objects recovered")
                return []

        # ─────────────────────────────

        if not isinstance(briefs, list):
            print("   ⚠️ [Deal Intel] Response is not a list")
            return []

        brief_map = {b.get("ticker", "").upper(): b for b in briefs}

        result = []
        for comp in comps:
            ticker = comp.get("Ticker", "").upper()
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

        priorities = sum(1 for r in result if r["approach_rec"] == "PRIORITY")
        strategic = sum(1 for r in result if r["tier"] == "STRATEGIC_BUYER")

        print(f"   🧠 [Deal Intel] {priorities} PRIORITY | {strategic} STRATEGIC_BUYER")

        return result

    except Exception as e:
        print(f"   ⚠️ [Deal Intel] Failed: {type(e).__name__}: {e}")
        return []

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