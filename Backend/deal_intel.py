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

def generate_deal_intelligence(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    comps: list[dict],
) -> list[dict]:

    print("\n" + "="*60)
    print("🧠 DEAL INTEL START")
    print(f"Target: {target_name} ({target_ticker})")
    print(f"Comps received: {len(comps)}")
    print("="*60)

    if not model:
        print("❌ Gemini model NOT available")
        return []

    if not comps:
        print("⚠️ No comps provided")
        return []

    # ─────────────────────────────
    # Tier 1 (comparables reales)
    # ─────────────────────────────
    tier1 = set()

    if target_ticker:
        tier1.add(target_ticker.upper())

    for c in comps:
        t = str(c.get("Ticker") or c.get("ticker") or "").upper()
        if t:
            tier1.add(t)

    print(f"🚫 Tier1 detected ({len(tier1)}): {list(tier1)}")

    # ─────────────────────────────
    # PROMPT (igual al tuyo)
    # ─────────────────────────────
    def build_prompt(target_name, target_ticker, target_industry):
        return f"""
Return ONLY a valid JSON array of exactly 10-15 objects. 
Role: Senior M&A Associate at Deloitte.
Target: {target_name} ({target_ticker})
Industry: {target_industry}

Task: Identify and classify potential acquirers/comparables into 3 Tiers:

1. TIER_1 (Direct Competitors): Companies with the same core business and overlapping market share.
2. TIER_2 (Strategic/Vertical): Generalists, companies with shared business units, or those that could generate economies of scale/synergies (e.g., supply chain integration, in-house production).
3. TIER_3 (Financial Sponsors): Private Equity firms or major Institutional Investors interested in this sector.

Each JSON object MUST follow this structure:
{{
  "ticker": "TICKER",
  "name": "Company Name",
  "tier": "TIER_1" | "TIER_2" | "TIER_3",
  "deal_thesis": "1-2 sentences explaining the strategic fit (20-40 words).",
  "strategic_rationale": "Detailed explanation of synergies or investment thesis (30-60 words)."
}}

Rules:
- Strictly NO prose or markdown.
- Must include at least 3 companies for EACH Tier.
- Ensure 'deal_thesis' and 'strategic_rationale' sound professional and data-driven.
- Focus on LATAM relevance if applicable.
- DO NOT include companies already listed as direct competitors.

Return ONLY the JSON array.
"""

    # ─────────────────────────────
    # AI CALL
    # ─────────────────────────────
    def call_ai(prompt, label):
        print(f"\n🚀 CALL [{label}]")

        try:
            r = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.35,
                    "max_output_tokens": 1200,
                    "response_mime_type": "application/json",
                },
            )

            text = r.text if r else None

            print(f"🧠 RAW [{label}]:\n{text[:500] if text else 'EMPTY'}\n")

            return text

        except Exception as e:
            print(f"❌ AI error: {e}")
            return None

    # ─────────────────────────────
    # PARSER ROBUSTO (FIX CLAVE)
    # ─────────────────────────────
    def extract(text):
        if not text:
            return []

        clean = text.strip()

        if "```" in clean:
            clean = clean.replace("```json", "").replace("```", "")

        # intento directo
        try:
            data = json.loads(clean)
            if isinstance(data, list):
                print(f"✅ Parsed objects (direct): {len(data)}")
                return data
        except:
            pass

        # fallback buscando array
        try:
            start = clean.find("[")
            end = clean.rfind("]") + 1
            if start != -1 and end != -1:
                data = json.loads(clean[start:end])
                print(f"✅ Parsed objects (fallback): {len(data)}")
                return data
        except:
            pass

        print("❌ Could not parse JSON")
        return []

    # ─────────────────────────────
    # EXECUTION
    # ─────────────────────────────
    prompt = build_prompt(target_name, target_ticker, target_industry)

    raw = call_ai(prompt, "MAIN")
    data = extract(raw)

    if not data:
        print("⚠️ RETRY")
        raw = call_ai(prompt, "RETRY")
        data = extract(raw)

    if not data:
        print("❌ AI FAILED")
        return []

    # ─────────────────────────────
    # FILTRO FINAL
    # ─────────────────────────────
    results = []

    for obj in data:
        ticker = str(obj.get("ticker", "")).upper().strip()
        tier = str(obj.get("tier", "")).strip()

        if not ticker:
            continue

        if ticker in tier1:
            print(f"❌ Removed Tier1 duplicate: {ticker}")
            continue

        results.append({
            "ticker": ticker,
            "name": obj.get("name", ""),
            "tier": tier,
            "deal_thesis": obj.get("deal_thesis", ""),
            "strategic_rationale": obj.get("strategic_rationale", ""),
        })

    # dedup
    seen = set()
    clean = []
    for r in results:
        if r["ticker"] in seen:
            continue
        seen.add(r["ticker"])
        clean.append(r)

    print(f"\n🧠 FINAL ({len(clean)}): {clean}")
    print("="*60 + "\n")

    return clean
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