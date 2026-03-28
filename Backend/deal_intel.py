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
import json
import re

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

    print("   🧠 [Deal Intel] Generating Tier 2 & 3 buyers (NO Tier 1)...")

    # ─────────────────────────────
    # CALL AI
    # ─────────────────────────────
    def call_ai(prompt):
        try:
            r = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 700,
                    "response_mime_type": "application/json",
                },
            )
            return r.text if r else None
        except Exception as e:
            print(f"   ❌ Gemini error: {e}")
            return None

    # ─────────────────────────────
    # PARSER ROBUSTO
    # ─────────────────────────────
    def extract(text):
        if not text:
            return []

        text = text.strip()

        if "```" in text:
            text = text.replace("```json", "").replace("```", "")

        matches = re.findall(r"\{.*?\}", text, re.DOTALL)

        out = []
        for m in matches:
            try:
                obj = json.loads(m)
                if isinstance(obj, dict):
                    out.append(obj)
            except:
                continue

        return out

    # ─────────────────────────────
    # PROMPT PRINCIPAL (BALANCEADO)
    # ─────────────────────────────
    prompt_main = f"""
Return a JSON array with exactly 3 buyers.

Target: {target_name} ({target_ticker})
Industry: {target_industry}

Rules:
- Only TIER_2 or TIER_3
- Each field max 15 words
- Be specific (no generic text)
- No explanations
- No markdown
- Valid JSON only

Format:
[
  {{
    "ticker": "WMT",
    "tier": "TIER_2",
    "deal_thesis": "LATAM expansion and logistics scale.",
    "strategic_rationale": "Distribution and cross-sell synergies."
  }}
]
"""

    raw = call_ai(prompt_main)
    print(f"\n🧠 RAW:\n{str(raw)[:400]}\n")

    data = extract(raw)

    # ─────────────────────────────
    # RETRY INTELIGENTE
    # ─────────────────────────────
    if not data:
        print("   ⚠️ retrying with compact prompt")

        prompt_retry = f"""
Return ONLY valid JSON.

3 buyers.
Very short fields.

[
{{"ticker":"WMT","tier":"TIER_2","deal_thesis":"Scale LATAM","strategic_rationale":"Logistics synergies"}},
{{"ticker":"AMZN","tier":"TIER_2","deal_thesis":"Market expansion","strategic_rationale":"Cross-sell growth"}},
{{"ticker":"KKR","tier":"TIER_3","deal_thesis":"PE buyout","strategic_rationale":"Value creation"}}
]
"""
        raw = call_ai(prompt_retry)
        print(f"\n🧠 RETRY RAW:\n{str(raw)[:400]}\n")

        data = extract(raw)

    if not data:
        print("   ⚠️ no valid output after retry")
        return []

    # ─────────────────────────────
    # NORMALIZACIÓN
    # ─────────────────────────────
    results = []

    for obj in data:
        ticker = str(obj.get("ticker", "")).upper().strip()
        tier = str(obj.get("tier", "TIER_2")).strip()

        if not ticker:
            continue

        if tier not in ["TIER_2", "TIER_3"]:
            continue

        results.append({
            "ticker": ticker,
            "tier": tier,
            "deal_thesis": str(obj.get("deal_thesis", "")).strip(),
            "strategic_rationale": str(obj.get("strategic_rationale", "")).strip(),
        })

    # ─────────────────────────────
    # LIMIT + ORDEN (DEMO READY)
    # ─────────────────────────────
    results = results[:3]

    tier_order = {"TIER_2": 0, "TIER_3": 1}
    results.sort(key=lambda x: tier_order.get(x["tier"], 99))

    if len(results) < 3:
        print(f"   ⚠️ only {len(results)} buyers generated (expected 3)")

    print(f"   🧠 [Deal Intel] Generated {len(results)} buyers")

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