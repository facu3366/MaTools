"""
🧠 DEAL INTELLIGENCE — DealDesk v3
====================================
M&A Intelligence: 3-Tier classification with real strategic analysis.
- Tier 1: Direct Competitors (from comps table)
- Tier 2: Adjacent Synergies (injected by engine — vertical/horizontal)
- Tier 3: Financial Sponsors / PE (injected by engine)
- Primary: Google Gemini 1.5 Flash
- Fallback: Curated mock data (demo never fails)
"""

import os
import json
import logging
import time
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
from datetime import datetime, timedelta, timezone
DATABASE_URL = os.getenv("DATABASE_URL")
CACHE_TTL_DAYS = 7

def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _cache_key(target_ticker, target_industry):
    return f"{target_ticker}_{target_industry}".lower()


def _get_from_cache(key):
    try:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT data, created_at
            FROM ai_cache
            WHERE cache_key = %s
        """, (key,))

        row = cur.fetchone()

        cur.close()
        conn.close()

        if not row:
            return None

        data, created_at = row

        if datetime.now(timezone.utc) - created_at > timedelta(days=CACHE_TTL_DAYS):
            print("   ⏳ Cache expired")
            return None

        print("   💾 CACHE HIT")
        return json.loads(data)

    except Exception as e:
        print(f"   ⚠️ Cache read error: {e}")
        return None


def _save_to_cache(key, data):
    try:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO ai_cache (cache_key, data, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (cache_key)
            DO UPDATE SET data = EXCLUDED.data, created_at = NOW()
        """, (key, json.dumps(data)))

        conn.commit()
        cur.close()
        conn.close()

        print("   💾 Saved to cache")

    except Exception as e:
        print(f"   ⚠️ Cache save error: {e}")


logger = logging.getLogger(__name__)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_KEY:
    raise RuntimeError("GEMINI_API_KEY no está configurada en Railway")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

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
# TIER 2 & 3 CANDIDATES BY INDUSTRY
# These get INJECTED into the analysis alongside comps
# ─────────────────────────────────────────────

TIER2_CANDIDATES = {
    "Internet Retail": [
        {"ticker": "WMT", "name": "Walmart", "rationale": "Physical retail + logistics integration, last-mile delivery economies of scale"},
        {"ticker": "V", "name": "Visa", "rationale": "Fintech integration — acquiring payment infrastructure in emerging markets"},
        {"ticker": "FDX", "name": "FedEx", "rationale": "Vertical integration into last-mile delivery, logistics infrastructure"},
        {"ticker": "UBER", "name": "Uber", "rationale": "Super App convergence — rides + eats + payments + retail ecosystem"},
        {"ticker": "GOOGL", "name": "Alphabet (Google)", "rationale": "Google Shopping + Cloud + Retail Media data monetization"},
        {"ticker": "MA", "name": "Mastercard", "rationale": "Payment network expansion into underbanked LATAM markets"},
    ],
    "Auto Manufacturers": [
        {"ticker": "ALB", "name": "Albemarle", "rationale": "Lithium supply chain vertical integration for EV batteries"},
        {"ticker": "GOOGL", "name": "Alphabet (Waymo)", "rationale": "Autonomous driving technology convergence"},
        {"ticker": "AAPL", "name": "Apple", "rationale": "Apple Car project — technology + brand + ecosystem integration"},
        {"ticker": "ENPH", "name": "Enphase Energy", "rationale": "Solar + EV charging infrastructure synergy"},
        {"ticker": "UBER", "name": "Uber", "rationale": "Ride-sharing fleet electrification, autonomous vehicle deployment"},
    ],
    "Software - Application": [
        {"ticker": "GOOGL", "name": "Alphabet", "rationale": "Cloud infrastructure + AI integration + distribution"},
        {"ticker": "AMZN", "name": "Amazon (AWS)", "rationale": "Cloud cross-selling, enterprise customer base expansion"},
        {"ticker": "ACN", "name": "Accenture", "rationale": "Implementation services + consulting integration"},
        {"ticker": "IBM", "name": "IBM", "rationale": "Enterprise AI + hybrid cloud strategy acceleration"},
    ],
    "Semiconductors": [
        {"ticker": "AAPL", "name": "Apple", "rationale": "Vertical integration of chip design + manufacturing"},
        {"ticker": "AMZN", "name": "Amazon (AWS)", "rationale": "Custom silicon for cloud, AI inference chips"},
        {"ticker": "MSFT", "name": "Microsoft", "rationale": "AI chip supply security for Azure + Copilot"},
        {"ticker": "GOOGL", "name": "Alphabet", "rationale": "TPU expansion, AI training infrastructure"},
    ],
    "Health Care Plans": [
        {"ticker": "AMZN", "name": "Amazon (One Medical)", "rationale": "Healthcare delivery + pharmacy + insurance integration"},
        {"ticker": "CVS", "name": "CVS Health", "rationale": "Retail clinic + PBM + insurance vertical integration"},
        {"ticker": "WMT", "name": "Walmart Health", "rationale": "Low-cost healthcare delivery at scale"},
    ],
    "_default": [
        {"ticker": "GOOGL", "name": "Alphabet", "rationale": "Technology + data integration across industries"},
        {"ticker": "AMZN", "name": "Amazon", "rationale": "Distribution + cloud + logistics platform synergies"},
        {"ticker": "MSFT", "name": "Microsoft", "rationale": "Enterprise software + AI + cloud integration"},
    ],
}

TIER3_CANDIDATES = [
    {"ticker": "SFTBY", "name": "SoftBank Vision Fund", "rationale": "Lead investor in LATAM tech ecosystems, understands asset-light scalability"},
    {"ticker": "BLK", "name": "BlackRock", "rationale": "Largest asset manager globally, capacity for take-private to unlock subsidiary value (eg fintech spin-off)"},
    {"ticker": "KKR", "name": "KKR & Co.", "rationale": "LBO specialists — could spin off high-growth units at premium valuations"},
    {"ticker": "APO", "name": "Apollo Global Management", "rationale": "Opportunistic PE — targets undervalued tech platforms with strong cash flow"},
    {"ticker": "BX", "name": "Blackstone", "rationale": "Largest PE firm globally, infrastructure + tech crossover expertise"},
    {"ticker": "CG", "name": "Carlyle Group", "rationale": "Deep emerging markets expertise, growth equity strategy"},
    {"ticker": "TPG", "name": "TPG Inc.", "rationale": "Tech-focused PE, Rise Fund ESG angle for financial inclusion"},
]


def _get_tier2_for_industry(industry: str) -> list[dict]:
    if not industry:
        return TIER2_CANDIDATES["_default"]
    for key, candidates in TIER2_CANDIDATES.items():
        if key == "_default":
            continue
        if key.lower() in industry.lower() or industry.lower() in key.lower():
            return candidates
    return TIER2_CANDIDATES["_default"]


# ─────────────────────────────────────────────
# NORMALIZE FIELDS
# ─────────────────────────────────────────────

def _normalize_comp(c: dict) -> dict:
    return {
        "ticker": c.get("Ticker") or c.get("ticker") or "???",
        "name": c.get("Empresa") or c.get("name") or c.get("ticker") or "???",
        "industry": c.get("Industria") or c.get("industry") or "N/A",
        "country": c.get("País") or c.get("Pais") or c.get("country") or "N/A",
        "revenue": c.get("Revenue ($mm)") or c.get("revenue") or 0,
        "ebitda": c.get("EBITDA ($mm)") or c.get("ebitda") or 0,
        "ev": c.get("EV ($mm)") or c.get("ev") or 0,
    }


# ─────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────

DEAL_INTEL_PROMPT = """You are a Senior M&A Consultant at Deloitte preparing a deal intelligence brief for a client pitch book. Your analysis must be specific, data-driven, and worthy of a VP-level presentation.

TARGET COMPANY:
- Name: {target_name} ({target_ticker})
- Industry: {target_industry}
- Revenue: ${target_revenue:,.0f}M USD

═══ TIER 1 CANDIDATES (Direct Competitors — from comps analysis): ═══
{tier1_text}

═══ TIER 2 CANDIDATES (Adjacent Synergies — vertical/horizontal integration): ═══
{tier2_text}

═══ TIER 3 CANDIDATES (Financial Sponsors / Private Equity): ═══
{tier3_text}

For EACH company above, return a JSON object:
- "ticker": string
- "tier": "STRATEGIC_BUYER" (Tier 1), "ADJACENT_SYNERGY" (Tier 2), or "FINANCIAL_SPONSOR" (Tier 3)
- "deal_thesis": 2-3 sentences. Be SPECIFIC: mention revenue numbers, geographic markets, product overlaps, technology gaps. Think like a Deloitte M&A consultant.
- "strategic_rationale": 1 sentence on value creation (cost synergies $X, revenue synergies, vertical integration, ecosystem play)
- "risks": 1-2 specific risks (regulatory/antitrust, cultural, financial capacity, integration complexity)
- "expansion_signal": "HIGH", "MEDIUM", or "LOW"
- "expansion_note": 1 sentence with evidence (recent acquisitions, capex trends, management commentary)
- "approach_rec": "PRIORITY", "SECONDARY", or "MONITOR"

RULES:
1. Keep each company in its designated tier (Tier 1/2/3 as labeled above).
2. PRIORITY = has means + motive + strategic fit. Maximum 3-4 companies.
3. Be brutally specific. "Market consolidation" is not enough. Say "Combined 35% market share in Brazilian e-commerce would create pricing power in electronics category."
4. For Tier 3 (PE), focus on financial engineering: LBO capacity, spin-off potential, multiple arbitrage.

Return ONLY a valid JSON array. No markdown fences. No explanation."""


def _build_tier1_text(comps: list[dict]) -> str:
    lines = []
    for c in comps[:12]:
        n = _normalize_comp(c)
        lines.append(f"- {n['ticker']}: {n['name']} | {n['industry']} | {n['country']} | Rev: ${n['revenue']:,.0f}M | EV: ${n['ev']:,.0f}M")
    return "\n".join(lines) if lines else "No Tier 1 candidates available."


def _build_tier2_text(candidates: list[dict]) -> str:
    lines = []
    for c in candidates[:6]:
        lines.append(f"- {c['ticker']}: {c['name']} | Context: {c['rationale']}")
    return "\n".join(lines) if lines else "No Tier 2 candidates available."


def _build_tier3_text() -> str:
    lines = []
    for c in TIER3_CANDIDATES[:5]:
        lines.append(f"- {c['ticker']}: {c['name']} | Context: {c['rationale']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# CALL GEMINI
# ─────────────────────────────────────────────

def _call_gemini(prompt: str) -> str | None:
    if not GEMINI_KEY:
        return None

    try:
        print(f"   🧠 Calling Gemini 1.5 Flash...")
        response = requests.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 4096,
                }
            },
            timeout=60,
        )

        if response.status_code != 200:
            print(f"   ❌ Gemini HTTP {response.status_code}: {response.text[:300]}")
            return None

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if text:
            print(f"   ✅ Gemini: {len(text)} chars")
        return text or None

    except Exception as e:
        print(f"   ❌ Gemini error: {e}")
        return None


def _parse_response(raw: str) -> list[dict]:
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1] if "\n" in clean else clean[3:]
    if clean.endswith("```"):
        clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()
    start = clean.find("[")
    end = clean.rfind("]")
    if start != -1 and end != -1 and end > start:
        clean = clean[start:end + 1]
    return json.loads(clean)


# ─────────────────────────────────────────────
# MOCK FALLBACK — ALL 3 TIERS ALWAYS PRESENT
# ─────────────────────────────────────────────

def _generate_mock_briefs(comps: list[dict], target_name: str, target_industry: str, target_revenue: float) -> list[dict]:
    print("   🎭 [Mock] Generating 3-tier fallback briefs...")
    result = []

    # Tier 1: from actual comps
    for i, c in enumerate(comps[:8]):
        n = _normalize_comp(c)
        rev = n["revenue"] or 0
        result.append({
            "ticker": n["ticker"].upper(),
            "tier": "STRATEGIC_BUYER",
            "deal_thesis": f"{n['name']} is a direct competitor in {n['industry']} with ${rev:,.0f}M revenue. Acquisition would consolidate market share and create pricing power in overlapping segments.",
            "strategic_rationale": f"Cost synergies estimated at 15-20% of combined SG&A from eliminating duplicate operations.",
            "risks": "Antitrust scrutiny in overlapping markets. Integration of competing product lines and technology stacks.",
            "expansion_signal": "HIGH" if rev > 50000 else "MEDIUM",
            "expansion_note": "Active acquirer" if rev > 50000 else "Selective M&A, primarily organic growth.",
            "approach_rec": "PRIORITY" if i < 2 else "SECONDARY",
        })

    # Tier 2: injected strategic synergies
    tier2 = _get_tier2_for_industry(target_industry)
    for c in tier2[:4]:
        result.append({
            "ticker": c["ticker"],
            "tier": "ADJACENT_SYNERGY",
            "deal_thesis": f"{c['name']} represents a strategic synergy opportunity: {c['rationale']}. Combined with {target_name}'s ${target_revenue:,.0f}M revenue base, the transaction would unlock significant cross-selling and ecosystem value.",
            "strategic_rationale": c["rationale"],
            "risks": "Cross-industry integration complexity. Different operational cultures and KPIs.",
            "expansion_signal": "HIGH",
            "expansion_note": "Active in adjacent acquisitions and strategic partnerships.",
            "approach_rec": "SECONDARY",
        })

    # Tier 3: PE / financial sponsors
    for c in TIER3_CANDIDATES[:3]:
        result.append({
            "ticker": c["ticker"],
            "tier": "FINANCIAL_SPONSOR",
            "deal_thesis": f"{c['name']}: {c['rationale']}. A take-private or growth equity investment in {target_name} could unlock value through financial engineering and subsidiary optimization.",
            "strategic_rationale": "Financial engineering: potential spin-off of high-growth units, multiple arbitrage, and operational optimization.",
            "risks": "Leveraged structure limits operational flexibility. Exit timeline pressure (3-5 year horizon).",
            "expansion_signal": "HIGH",
            "expansion_note": "Actively deploying capital, recent fund raises indicate dry powder availability.",
            "approach_rec": "MONITOR",
        })

    print(f"   🎭 [Mock] {len(result)} briefs: {sum(1 for r in result if r['tier']=='STRATEGIC_BUYER')} T1 + {sum(1 for r in result if r['tier']=='ADJACENT_SYNERGY')} T2 + {sum(1 for r in result if r['tier']=='FINANCIAL_SPONSOR')} T3")
    return result


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def generate_deal_intelligence(
    target_ticker: str,
    target_name: str,
    target_industry: str,
    target_revenue: float,
    comps: list[dict],
) -> list[dict]:
    if not comps:
        return []

    print(f"   🧠 [Deal Intel v3] {target_name} ({target_ticker}) | {target_industry} | {len(comps)} comps")

    # ─────────────────────────────
    # CACHE KEY
    # ─────────────────────────────
    key = f"{target_ticker}_{target_industry}".lower()

    # ── 1. TRY CACHE ──
    try:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT data, created_at
            FROM ai_cache
            WHERE cache_key = %s
        """, (key,))

        row = cur.fetchone()

        cur.close()
        conn.close()

        if row:
            data, created_at = row

            if datetime.now(timezone.utc) - created_at <= timedelta(days=CACHE_TTL_DAYS):
                print("   💾 CACHE HIT")
                return json.loads(data)
            else:
                print("   ⏳ Cache expired")

    except Exception as e:
        print(f"   ⚠️ Cache read error: {e}")

    # Get Tier 2/3 candidates
    tier2_candidates = _get_tier2_for_industry(target_industry)

    # ── 2. TRY GEMINI ──
    if GEMINI_KEY:
        prompt = DEAL_INTEL_PROMPT.format(
            target_name=target_name,
            target_ticker=target_ticker,
            target_industry=target_industry or "Unknown",
            target_revenue=target_revenue or 0,
            tier1_text=_build_tier1_text(comps),
            tier2_text=_build_tier2_text(tier2_candidates),
            tier3_text=_build_tier3_text(),
        )

        try:
            t0 = time.time()
            raw = _call_gemini(prompt)
            elapsed = time.time() - t0

            if raw:
                briefs = _parse_response(raw)
                if isinstance(briefs, list) and len(briefs) > 0:
                    # Normalize all tickers to uppercase
                    for b in briefs:
                        b["ticker"] = b.get("ticker", "").upper()
                        b.setdefault("tier", "STRATEGIC_BUYER")
                        b.setdefault("deal_thesis", "")
                        b.setdefault("strategic_rationale", "")
                        b.setdefault("risks", "")
                        b.setdefault("expansion_signal", "MEDIUM")
                        b.setdefault("expansion_note", "")
                        b.setdefault("approach_rec", "SECONDARY")

                    t1 = sum(1 for b in briefs if b["tier"] == "STRATEGIC_BUYER")
                    t2 = sum(1 for b in briefs if b["tier"] == "ADJACENT_SYNERGY")
                    t3 = sum(1 for b in briefs if b["tier"] == "FINANCIAL_SPONSOR")

                    print(f"   🧠 ✅ Gemini: {len(briefs)} briefs in {elapsed:.1f}s | T1={t1} T2={t2} T3={t3}")

                    # 💾 SAVE GEMINI RESULT
                    try:
                        conn = _get_conn()
                        cur = conn.cursor()

                        cur.execute("""
                            INSERT INTO ai_cache (cache_key, data, created_at)
                            VALUES (%s, %s, NOW())
                            ON CONFLICT (cache_key)
                            DO UPDATE SET data = EXCLUDED.data, created_at = NOW()
                        """, (key, json.dumps(briefs)))

                        conn.commit()
                        cur.close()
                        conn.close()

                        print("   💾 Saved Gemini result")

                    except Exception as e:
                        print(f"   ⚠️ Cache save error: {e}")

                    return briefs

        except json.JSONDecodeError as e:
            print(f"   ⚠️ JSON parse error: {e}")
        except Exception as e:
            print(f"   ⚠️ Gemini failed: {e}")

    # ── 3. FALLBACK ──
    print("   🎭 Using fallback")

    fallback = _generate_mock_briefs(
        comps, target_name, target_industry, target_revenue
    )

    # 💾 SAVE FALLBACK TAMBIÉN
    try:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO ai_cache (cache_key, data, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (cache_key)
            DO UPDATE SET data = EXCLUDED.data, created_at = NOW()
        """, (key, json.dumps(fallback)))

        conn.commit()
        cur.close()
        conn.close()

        print("   💾 Saved fallback result")

    except Exception as e:
        print(f"   ⚠️ Cache save error: {e}")

    return fallback
# ─────────────────────────────────────────────
# ENDPOINT
# ─────────────────────────────────────────────

@router.post("/comps/deal-intel")
def get_deal_intelligence(request: DealIntelRequest):
    briefs = generate_deal_intelligence(
        target_ticker=request.target_ticker,
        target_name=request.target_name,
        target_industry=request.target_industry,
        target_revenue=request.target_revenue,
        comps=request.comps,
    )

    source = "gemini" if any(b.get("deal_thesis", "").count(".") > 2 for b in briefs) else "mock"

    return {
        "target": request.target_ticker,
        "n_briefs": len(briefs),
        "briefs": briefs,
        "source": source,
        "tiers": {
            "strategic_buyers": sum(1 for b in briefs if b["tier"] == "STRATEGIC_BUYER"),
            "adjacent_synergies": sum(1 for b in briefs if b["tier"] == "ADJACENT_SYNERGY"),
            "financial_sponsors": sum(1 for b in briefs if b["tier"] == "FINANCIAL_SPONSOR"),
        }
    }