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
try:
    model = genai.GenerativeModel("gemini-2.5-flash")
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
                "max_output_tokens": 800,  # 🔥 bajamos para evitar corte
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

    # ─────────────────────────────
    # VALIDACIONES
    # ─────────────────────────────
    if not model:
        print("   ⚠️ [Deal Intel] Gemini not available")
        return []

    if not comps:
        return []

    print(f"   🧠 [Deal Intel] Generating Tier 2 & 3 buyers (NO Tier 1)...")

    # ─────────────────────────────
    # CONTEXTO (NO OUTPUT)
    # ─────────────────────────────
    context_companies = []

    for c in comps[:10]:
        ticker = c.get("Ticker", "")
        name = c.get("Empresa", ticker)
        industry = c.get("Industria", "N/A")
        rev = c.get("Revenue ($mm)", 0)

        context_companies.append(
            f"- {ticker}: {name} | {industry} | Revenue ${rev}M"
        )

    comps_text = "\n".join(context_companies)

    # ─────────────────────────────
    # PROMPT (CLAVE)
    # ─────────────────────────────
    prompt = f"""
You are a senior M&A consultant at Deloitte working on a live sell-side mandate.

TARGET:
{target_name} ({target_ticker})
Industry: {target_industry}
Revenue: ${target_revenue}M

IMPORTANT:
- Tier 1 competitors are ALREADY identified externally.
- DO NOT return Tier 1 companies.
- Your job is to identify NEW potential buyers.

TIER DEFINITIONS:
- TIER_2: Strategic buyers (synergies, adjacency, scale, cross-sell, geography, technology, distribution)
- TIER_3: Financial sponsors (Private Equity, buyout funds, roll-ups)

CONTEXT (existing comps):
{comps_text}

TASK:
Return a JSON array of potential buyers (NOT limited to comps).

Each object must contain:
- "ticker"
- "tier": "TIER_2" or "TIER_3"
- "deal_thesis": exactly 2 lines explaining why they would buy
- "strategic_rationale": 1 short paragraph explaining value creation

RULES:
- DO NOT include Tier 1 competitors
- You can include companies NOT in the list
- Be commercially sharp and realistic
- Avoid generic phrases
- No markdown
- Return ONLY valid JSON

Example:
[
  {{
    "ticker": "XYZ",
    "tier": "TIER_2",
    "deal_thesis": "Expansion into LATAM with strong commercial overlap. Improves scale and logistics density.",
    "strategic_rationale": "The deal would unlock synergies in distribution, procurement and customer acquisition, while improving operating leverage."
  }}
]
"""

    results = []

    try:
        raw = _call_ai(prompt)

        if not raw:
            print("   ⚠️ empty AI response")
            return []

        print(f"\n🧠 RAW:\n{raw[:500]}\n")

        clean = raw.strip()

        # ─────────────────────────────
        # LIMPIEZA
        # ─────────────────────────────
        if "```" in clean:
            clean = clean.replace("```json", "").replace("```", "").strip()

        start = clean.find("[")
        end = clean.rfind("]")

        if start == -1 or end == -1:
            print("   ⚠️ invalid JSON format")
            return []

        clean = clean[start:end + 1]

        data = json.loads(clean)

        for obj in data:
            results.append({
                "ticker": str(obj.get("ticker", "N/A")).upper(),
                "tier": obj.get("tier", "TIER_2"),
                "deal_thesis": obj.get("deal_thesis", ""),
                "strategic_rationale": obj.get("strategic_rationale", ""),
            })

    except Exception as e:
        print(f"   ❌ Deal Intel error: {e}")
        return []

    print(f"   🧠 [Deal Intel] Generated {len(results)} Tier 2/3 buyers")

    return results
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