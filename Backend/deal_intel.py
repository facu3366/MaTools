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
                "temperature": 0.25,
                "max_output_tokens": 800,  # importante
            },
        )
        return response.text

    except Exception as e:
        print(f"❌ Gemini failed: {e}")
        return None
# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────
import re
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
    # Tier 1
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
    # PROMPT
    # ─────────────────────────────
    def build_prompt(target_name, target_ticker, target_industry):
        prompt = f"""
Return ONLY a valid JSON array of exactly 10-15 objects. 
Target: {target_name} ({target_ticker})
Industry: {target_industry}

Each object:
{{
  "ticker": "...",
  "name": "...",
  "tier": "TIER_1" | "TIER_2" | "TIER_3",
  "deal_thesis": "...",
  "strategic_rationale": "..."
}}

Rules:
- No markdown
- No explanation
- JSON only
"""
        return prompt

    prompt = build_prompt(target_name, target_ticker, target_industry)

    print("\n🧾 PROMPT PREVIEW (first 400 chars):")
    print(prompt[:400])
    print("—" * 40)

    # ─────────────────────────────
    # CALL AI
    # ─────────────────────────────
    raw = _call_ai(prompt)

    print("\n🧠 RAW RESPONSE TYPE:", type(raw))
    print("🧠 RAW LENGTH:", len(raw) if raw else 0)

    if not raw:
        print("❌ EMPTY RESPONSE FROM AI")
        return []

    print("\n🧠 RAW PREVIEW (first 500 chars):")
    print(raw[:500])
    print("—" * 40)

    # ─────────────────────────────
    # CLEAN
    # ─────────────────────────────
    clean = raw.strip()
    clean = clean.replace("```json", "").replace("```", "")

    print("\n🧹 CLEANED PREVIEW:")
    print(clean[:500])
    print("—" * 40)

    # ─────────────────────────────
    # PARSER DEBUG STEP 1 (JSON directo)
    # ─────────────────────────────
    try:
        data = json.loads(clean)
        print(f"✅ DIRECT JSON PARSE OK: {len(data)} objects")
    except Exception as e:
        print("❌ DIRECT JSON PARSE FAILED")
        print("Error:", str(e))
        data = None

    # ─────────────────────────────
    # PARSER DEBUG STEP 2 (regex {})
    # ─────────────────────────────
    matches = re.findall(r"\{[^{}]*\}", clean)
    print(f"\n🔍 REGEX OBJECT MATCHES: {len(matches)}")

    parsed_objects = []

    for i, m in enumerate(matches):
        try:
            obj = json.loads(m)
            parsed_objects.append(obj)
        except Exception as e:
            print(f"❌ Failed parsing object {i}: {m[:80]}")

    print(f"✅ REGEX PARSED OBJECTS: {len(parsed_objects)}")

    # ─────────────────────────────
    # PARSER DEBUG STEP 3 (ticker split)
    # ─────────────────────────────
    chunks = re.split(r'"ticker"\s*:\s*"', clean)
    print(f"\n🧩 TICKER SPLIT CHUNKS: {len(chunks)}")

    rebuilt = []

    for i, chunk in enumerate(chunks[1:]):
        try:
            obj_str = '{"ticker":"' + chunk
            obj_str = obj_str.split("}")[0] + "}"
            obj = json.loads(obj_str)
            rebuilt.append(obj)
        except Exception:
            continue

    print(f"✅ REBUILT OBJECTS: {len(rebuilt)}")

    # ─────────────────────────────
    # FINAL SOURCE SELECTION
    # ─────────────────────────────
    if isinstance(data, list) and len(data) > 0:
        final_data = data
        print("🟢 USING DIRECT JSON")
    elif len(parsed_objects) > 0:
        final_data = parsed_objects
        print("🟡 USING REGEX OBJECTS")
    elif len(rebuilt) > 0:
        final_data = rebuilt
        print("🟠 USING REBUILT OBJECTS")
    else:
        print("❌ ALL PARSERS FAILED")
        return []

    # ─────────────────────────────
    # FILTER
    # ─────────────────────────────
    results = []

    for obj in final_data:
        ticker = str(obj.get("ticker", "")).upper().strip()

        if not ticker:
            print("⚠️ Skipping object without ticker:", obj)
            continue

        if ticker in tier1:
            print(f"❌ Removed Tier1 duplicate: {ticker}")
            continue

        results.append({
            "ticker": ticker,
            "name": obj.get("name", ""),
            "tier": obj.get("tier", ""),
            "deal_thesis": obj.get("deal_thesis", ""),
            "strategic_rationale": obj.get("strategic_rationale", ""),
        })

    # ─────────────────────────────
    # DEDUP
    # ─────────────────────────────
    seen = set()
    clean_final = []

    for r in results:
        if r["ticker"] in seen:
            print(f"⚠️ Duplicate removed: {r['ticker']}")
            continue
        seen.add(r["ticker"])
        clean_final.append(r)

    print(f"\n🧠 FINAL COUNT: {len(clean_final)}")
    print("🧠 FINAL DATA:", clean_final)
    print("="*60 + "\n")

    return clean_final
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