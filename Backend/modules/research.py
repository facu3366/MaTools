"""
🔬 EQUITY RESEARCH — Module (DealDesk)
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import anthropic
import json
import os
import io
import yfinance as yf
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

# ESTE ES EL CAMBIO CLAVE
router = APIRouter()

# Store last research results for PDF export
research_cache = {}

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class ResearchRequest(BaseModel):
    ticker: str
    fase: str

class PDFRequest(BaseModel):
    ticker: str


# ─────────────────────────────────────────────
# DATA FETCHER
# ─────────────────────────────────────────────

def get_company_data(ticker: str) -> dict:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        inc = stock.financials
        inc_q = stock.quarterly_financials
        bal = stock.balance_sheet
        cf = stock.cashflow
        hist = stock.history(period="1y")

        def safe_loc(df, label, n=4):
            if df is not None and label in df.index:
                return df.loc[label].tolist()[:n]
            return []

        def safe_dates(df, n=8):
            if df is not None and not df.empty:
                return [str(d.date()) for d in df.columns.tolist()[:n]]
            return []

        data = {
            "ticker": ticker,
            "nombre": info.get("longName", ticker),
            "sector": info.get("sector", "N/A"),
            "industria": info.get("industry", "N/A"),
            "pais": info.get("country", "N/A"),
            "moneda": info.get("currency", "USD"),
            "empleados": info.get("fullTimeEmployees"),
            "descripcion": info.get("longBusinessSummary", ""),

            # P&L
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "revenue": info.get("totalRevenue"),
            "ebitda": info.get("ebitda"),
            "net_income": info.get("netIncomeToCommon"),
            "fcf": info.get("freeCashflow"),
            "gross_margin": info.get("grossMargins"),
            "ebitda_margin": info.get("ebitdaMargins"),
            "operating_margin": info.get("operatingMargins"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),

            # Multiples
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "ev_revenue": info.get("enterpriseToRevenue"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "pb": info.get("priceToBook"),
            "ps": info.get("priceToSalesTrailing12Months"),

            # Balance
            "total_debt": info.get("totalDebt"),
            "total_cash": info.get("totalCash"),
            "beta": info.get("beta"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "current_price": info.get("currentPrice"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            "operating_cf": info.get("operatingCashflow"),
            "price_52w_high": info.get("fiftyTwoWeekHigh"),
            "price_52w_low": info.get("fiftyTwoWeekLow"),

            # Historical financials
            "revenue_hist": safe_loc(inc, "Total Revenue"),
            "ebitda_hist": safe_loc(inc, "EBITDA"),
            "net_income_hist": safe_loc(inc, "Net Income"),
            "operating_income_hist": safe_loc(inc, "Operating Income"),
            "gross_profit_hist": safe_loc(inc, "Gross Profit"),
            "rd_hist": safe_loc(inc, "Research Development"),
            "sga_hist": safe_loc(inc, "Selling General Administrative"),

            # Balance sheet
            "total_assets_hist": safe_loc(bal, "Total Assets"),
            "total_liabilities_hist": safe_loc(bal, "Total Liabilities Net Minority Interest") or safe_loc(bal, "Total Liab"),
            "total_equity_hist": safe_loc(bal, "Stockholders Equity") or safe_loc(bal, "Total Stockholders Equity"),

            # Cash flow
            "operating_cf_hist": safe_loc(cf, "Total Cash From Operating Activities") or safe_loc(cf, "Operating Cash Flow"),
            "capex_hist": safe_loc(cf, "Capital Expenditures") or safe_loc(cf, "Capital Expenditure"),
            "depreciation_hist": safe_loc(cf, "Depreciation"),

            # Quarterly
            "quarterly_revenue": safe_loc(inc_q, "Total Revenue", 8),
            "quarterly_dates": safe_dates(inc_q),

            # Performance
            "price_ytd_change": round((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 1) if not hist.empty and len(hist) > 1 else None,
        }
        return data
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


# ─────────────────────────────────────────────
# SYSTEM PROMPT — personalidad del analista
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Sos un Senior Equity Research Analyst con 15 años de experiencia en M&A Advisory y Equity Research en bancos tier-1 (Goldman Sachs, Morgan Stanley, JP Morgan). Trabajás para el equipo de M&A de Deloitte Argentina.

REGLAS ESTRICTAS:
1. SOLO usá los datos numéricos provistos. No inventes números. Si un dato falta, decí "N/D" o "No disponible".
2. Todos los montos en USD millones (M) o billones (B) según corresponda.
3. Los porcentajes siempre con 1 decimal.
4. Formato: usá headers con ##, tablas en markdown, bullet points con -.
5. Sé directo, sin disclaimers genéricos tipo "es importante considerar". Dá tu opinión profesional.
6. Cuando hagas proyecciones, SIEMPRE justificá cada supuesto con el dato histórico que lo respalda.
7. Escribí en español argentino profesional (no informal).
8. Las tablas deben tener alineación numérica y headers claros."""


# ─────────────────────────────────────────────
# PROMPTS v2 — calidad institucional
# ─────────────────────────────────────────────

def get_phase_prompt(fase, ticker, data):
    data_str = json.dumps(data, indent=2, default=str)
    nombre = data.get("nombre", ticker)
    moneda = data.get("moneda", "USD")

    prompts = {

        "fundamentals": f"""## INSTRUCCIÓN: FASE 1 — ANÁLISIS DE FUNDAMENTOS

**Empresa:** {nombre} ({ticker})
**Datos de mercado (fuente: Yahoo Finance, real-time):**
```json
{data_str}
```

Producí un análisis de fundamentos con esta estructura EXACTA:

## 1. Perfil de la Compañía
- Nombre, sector, industria, país, empleados, market cap.
- Descripción del negocio en 2-3 oraciones.

## 2. Revenue Drivers & Segmentación
- Revenue total y crecimiento YoY (usá revenue_hist para calcular la CAGR de los últimos 3-4 años).
- Si hay datos de segmentos en la descripción, desglosalos.
- Concentración geográfica y de clientes (inferir del sector/industria).

## 3. Estructura de Costos & Análisis de Márgenes
Construí esta tabla con los datos históricos:

| Métrica | FY-3 | FY-2 | FY-1 | LTM | Tendencia |
|---------|------|------|------|-----|-----------|
| Revenue ($M) | | | | | |
| Gross Margin % | | | | | |
| EBITDA Margin % | | | | | |
| Operating Margin % | | | | | |
| Net Margin % | | | | | |

Analizá si los márgenes se están expandiendo o comprimiendo y POR QUÉ.

## 4. Posición Financiera
- Total Debt vs Total Cash → Net Debt position.
- Net Debt / EBITDA (calculalo con los datos).
- Equity vs Debt mix (inferir de market_cap y total_debt).
- ¿La empresa es generadora o consumidora de caja? (usá operating_cf y fcf).

## 5. Riesgos Operativos (Top 5)
Para cada riesgo: nombre + 1 oración de por qué es relevante para ESTA empresa específicamente.

## 6. Estrategia de Management
- Nivel de inversión: Capex como % de revenue (usá capex_hist y revenue_hist).
- R&D intensity si hay datos.
- Capital allocation: ¿están reinvirtiendo, pagando deuda, o devolviendo capital?""",


        "earnings": f"""## INSTRUCCIÓN: FASE 2 — ANÁLISIS DE TENDENCIAS & EARNINGS

**Empresa:** {nombre} ({ticker})
**Datos de mercado:**
```json
{data_str}
```

Producí un análisis de tendencias con esta estructura EXACTA:

## 1. Tendencia de Revenue (Momentum Analysis)
- Revenue LTM: ${'{:,.0f}'.format(data.get('revenue', 0) or 0)}M
- Revenue Growth Rate: {data.get('revenue_growth', 'N/D')}
- Construí una tabla trimestral si hay datos en quarterly_revenue:

| Trimestre | Revenue ($M) | Var QoQ % | Var YoY % |
|-----------|-------------|-----------|-----------|

- ¿El growth está acelerando o desacelerando? Cuantificá.

## 2. Expansión / Compresión de Márgenes
- EBITDA Margin: {data.get('ebitda_margin', 'N/D')} → ¿Está en su máximo histórico o comprimiéndose?
- Operating Margin: {data.get('operating_margin', 'N/D')}
- Explicá los drivers: ¿es pricing power, eficiencia operativa, mix de producto, o leverage operativo?

## 3. Earnings Quality Score
Evaluá la calidad de las ganancias:
- Net Income vs Operating Cash Flow: Si OCF >> NI = alta calidad. Si NI >> OCF = red flag.
- FCF Conversion: FCF / Net Income ratio (calculalo).
- Accruals: ¿Hay diferencias significativas entre ganancias contables y caja?
- Dá un score: ALTA / MEDIA / BAJA calidad de earnings, con justificación numérica.

## 4. Señales Bullish (Top 3-4)
Para cada una: métrica específica + por qué es positiva.

## 5. Señales Bearish / Red Flags (Top 3-4)
Para cada una: métrica específica + nivel de riesgo (ALTO/MEDIO/BAJO).

## 6. Price Performance & Contexto de Mercado
- Precio actual: ${data.get('current_price', 'N/D')}
- 52-week high: ${data.get('price_52w_high', 'N/D')} | 52-week low: ${data.get('price_52w_low', 'N/D')}
- YTD change: {data.get('price_ytd_change', 'N/D')}%
- ¿Dónde está el precio vs su rango? ¿Near high, near low, mid-range?
- Beta: {data.get('beta', 'N/D')} → ¿Qué implica sobre la volatilidad?""",


        "dcf": f"""## INSTRUCCIÓN: FASE 3 — MODELO DCF COMPLETO

**Empresa:** {nombre} ({ticker})
**Datos de mercado:**
```json
{data_str}
```

Producí un modelo DCF profesional con esta estructura EXACTA:

## 1. Supuestos de Proyección (5 años)
Justificá CADA supuesto con el dato histórico que lo respalda:

| Supuesto | Valor | Justificación |
|----------|-------|---------------|
| Revenue Growth Y1 | X% | Basado en revenue_growth actual de {data.get('revenue_growth', 'N/D')} |
| Revenue Growth Y2-Y3 | X% | Convergencia a promedio sectorial |
| Revenue Growth Y4-Y5 | X% | Steady state |
| EBITDA Margin (estable) | X% | Basado en EBITDA margin actual de {data.get('ebitda_margin', 'N/D')} |
| Capex % Revenue | X% | Basado en capex_hist / revenue_hist |
| D&A % Revenue | X% | Basado en depreciation_hist / revenue_hist |
| Tax Rate | X% | Inferido de net_income / operating_income o estándar sectorial |
| Change in NWC % Rev | X% | Estándar sectorial |

## 2. Revenue Build (Proyección)

| Concepto | FY0 (LTM) | Y1 | Y2 | Y3 | Y4 | Y5 |
|----------|-----------|-----|-----|-----|-----|-----|
| Revenue ($M) | | | | | | |
| Growth % | | | | | | |

## 3. Bridge: Revenue → Unlevered Free Cash Flow

| Concepto | FY0 | Y1 | Y2 | Y3 | Y4 | Y5 |
|----------|-----|-----|-----|-----|-----|-----|
| Revenue | | | | | | |
| (-) COGS & OpEx | | | | | | |
| = EBITDA | | | | | | |
| (-) D&A | | | | | | |
| = EBIT | | | | | | |
| (-) Taxes on EBIT | | | | | | |
| = NOPAT | | | | | | |
| (+) D&A | | | | | | |
| (-) Capex | | | | | | |
| (-) Change in NWC | | | | | | |
| = Unlevered FCF | | | | | | |

## 4. WACC Calculation

| Componente | Valor | Fuente |
|-----------|-------|--------|
| Risk Free Rate | 4.50% | US 10Y Treasury |
| Equity Risk Premium | 5.50% | Damodaran |
| Beta | {data.get('beta', 'N/D')} | Yahoo Finance (2Y weekly) |
| Cost of Equity (Ke) | =calcular= | CAPM: Rf + Beta * ERP |
| Pre-tax Cost of Debt (Kd) | =estimar= | Basado en credit profile |
| Tax Rate | =estimar= | |
| Equity Weight | =calcular= | Market Cap / (Market Cap + Debt) |
| Debt Weight | =calcular= | Debt / (Market Cap + Debt) |
| **WACC** | =calcular= | Ke * We + Kd * (1-t) * Wd |

## 5. Terminal Value & Implied Valuation

| Método | Valor |
|--------|-------|
| Terminal Growth Rate | 2.5% |
| Terminal Value (Gordon Growth) | =calcular= |
| PV of FCFs (Y1-Y5) | =calcular= |
| PV of Terminal Value | =calcular= |
| Enterprise Value (Implied) | =calcular= |
| (-) Net Debt | =de los datos= |
| Equity Value | =calcular= |
| Shares Outstanding | {data.get('shares_outstanding', 'N/D')} |
| **Implied Price per Share** | =calcular= |
| Current Price | ${data.get('current_price', 'N/D')} |
| **Upside / Downside** | =calcular= |

## 6. Sensitivity Analysis
Tabla de sensibilidad: WACC (filas) vs Terminal Growth (columnas) → Implied Price

| WACC \\ TGR | 2.0% | 2.5% | 3.0% |
|-------------|------|------|------|
| WACC - 1% | | | |
| WACC base | | | |
| WACC + 1% | | | |""",


        "thesis": f"""## INSTRUCCIÓN: FASE 4 — TESIS DE INVERSIÓN

**Empresa:** {nombre} ({ticker})
**Datos de mercado:**
```json
{data_str}
```

Producí una nota de Equity Research de calidad institucional con esta estructura EXACTA:

## EXECUTIVE SUMMARY
- Recomendación: **[BUY / HOLD / SELL]**
- Target Price: $[XX] - $[XX] (rango basado en DCF + múltiplos)
- Upside/Downside: [X]% desde el precio actual de ${data.get('current_price', 'N/D')}
- Horizonte: 12 meses
- 2-3 oraciones con la tesis central.

## INVESTMENT HIGHLIGHTS (Top 4)
Para cada highlight:
- **Título del driver** — Explicación en 2-3 oraciones con datos numéricos que lo respalden.

## COMPETITIVE MOATS
- Tipo de moat: Network effects / Switching costs / Scale / Brand / IP / Cost advantage
- Duración estimada de la ventaja competitiva
- Principal amenaza a cada moat

## VALUATION SUMMARY — Múltiplos vs Peers

| Métrica | {ticker} | Peer 1 | Peer 2 | Sector Median | Premium/Discount |
|---------|----------|--------|--------|---------------|------------------|
| EV/Revenue | {data.get('ev_revenue', 'N/D')}x | | | | |
| EV/EBITDA | {data.get('ev_ebitda', 'N/D')}x | | | | |
| P/E (trailing) | {data.get('pe_trailing', 'N/D')}x | | | | |
| P/E (forward) | {data.get('pe_forward', 'N/D')}x | | | | |
| P/B | {data.get('pb', 'N/D')}x | | | | |

¿Está la empresa cara o barata vs peers? ¿El premium está justificado?

## KEY RISKS (Top 3)
Para cada riesgo:
- **Riesgo** — Probabilidad (ALTA/MEDIA/BAJA) | Impacto (ALTO/MEDIO/BAJO)
- Mitigante (si existe)

## CATALYSTS (Próximos 6-12 meses)
- Fecha estimada + evento + impacto esperado en el precio

## FINAL VERDICT
Párrafo de cierre de 3-4 oraciones: ¿comprás, mantenés o vendés? ¿Por qué? ¿Cuál es el factor #1 que cambiaría tu opinión?""",
    }
    return prompts.get(fase, "Fase no reconocida.")


# ─────────────────────────────────────────────
# RESEARCH ENDPOINT
# ─────────────────────────────────────────────

@router.post("/research")
def run_research_phase(request: ResearchRequest):
    ticker = request.ticker.upper()
    fase = request.fase.lower()

    valid = ["fundamentals", "earnings", "dcf", "thesis"]
    if fase not in valid:
        raise HTTPException(400, f"Fase inválida. Opciones: {valid}")
    if not ANTHROPIC_KEY:
        raise HTTPException(500, "ANTHROPIC_API_KEY no configurada.")

    print(f"\n🔬 Research [{fase.upper()}] → {ticker}")

    company_data = get_company_data(ticker)
    if "error" in company_data:
        raise HTTPException(404, f"Sin datos para {ticker}: {company_data['error']}")

    prompt = get_phase_prompt(fase, ticker, company_data)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = response.content[0].text
    except Exception as e:
        raise HTTPException(500, f"Error Claude API: {str(e)}")

    # Cache for PDF export
    if ticker not in research_cache:
        research_cache[ticker] = {"empresa": company_data.get("nombre", ticker), "data": company_data}
    research_cache[ticker][fase] = analysis

    return {
        "ticker": ticker,
        "fase": fase,
        "empresa": company_data.get("nombre", ticker),
        "analysis": analysis,
    }


# ─────────────────────────────────────────────
# PDF EXPORT
# ─────────────────────────────────────────────

@router.post("/research/pdf")
def export_research_pdf(request: PDFRequest):
    """Genera PDF profesional del research completo."""
    ticker = request.ticker.upper()

    if ticker not in research_cache:
        raise HTTPException(404, "No hay research en cache para este ticker. Corré el análisis primero.")

    cached = research_cache[ticker]
    empresa = cached.get("empresa", ticker)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable
    )
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Colors
    GOLD = HexColor("#8b7535")
    GOLD_LIGHT = HexColor("#d4c48a")
    INK = HexColor("#111111")
    MUTED = HexColor("#666666")
    LINE = HexColor("#e5e2dc")
    CREAM = HexColor("#faf8f0")
    GREEN = HexColor("#2d6a4f")

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.2*cm,
        rightMargin=2.2*cm,
        topMargin=2.5*cm,
        bottomMargin=2*cm,
    )

    # Styles
    styles = {
        "cover_eyebrow": ParagraphStyle(
            "cover_eyebrow", fontName="Helvetica", fontSize=8,
            leading=10, textColor=GOLD, spaceAfter=6,
            tracking=3,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", fontName="Helvetica-Bold", fontSize=28,
            leading=34, textColor=INK, spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontName="Helvetica", fontSize=10,
            leading=14, textColor=MUTED, spaceAfter=4,
        ),
        "phase_title": ParagraphStyle(
            "phase_title", fontName="Helvetica-Bold", fontSize=14,
            leading=18, textColor=INK, spaceBefore=16, spaceAfter=8,
        ),
        "phase_subtitle": ParagraphStyle(
            "phase_subtitle", fontName="Helvetica", fontSize=8,
            leading=10, textColor=GOLD, spaceAfter=12,
            tracking=2,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=11,
            leading=14, textColor=INK, spaceBefore=12, spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "h3", fontName="Helvetica-Bold", fontSize=10,
            leading=13, textColor=GOLD, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9,
            leading=13, textColor=INK, spaceAfter=6,
            alignment=TA_JUSTIFY,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=9,
            leading=13, textColor=INK, spaceAfter=3,
            leftIndent=12, bulletIndent=0,
        ),
        "footer": ParagraphStyle(
            "footer", fontName="Helvetica", fontSize=7,
            leading=9, textColor=MUTED, alignment=TA_CENTER,
        ),
    }

    story = []

    # ─── COVER PAGE ───
    story.append(Spacer(1, 3*cm))
    story.append(Paragraph("EQUITY RESEARCH  ·  DEEP ANALYSIS", styles["cover_eyebrow"]))
    story.append(Paragraph(f"{empresa}", styles["cover_title"]))
    story.append(Paragraph(f"Ticker: {ticker}", styles["cover_sub"]))
    story.append(Paragraph(f"Fecha: {datetime.now().strftime('%d de %B de %Y')}", styles["cover_sub"]))
    story.append(Paragraph("Analista: DealDesk M&A Intelligence", styles["cover_sub"]))
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=GOLD, spaceAfter=12))
    story.append(Spacer(1, 0.5*cm))

    # Key metrics summary box
    data = cached.get("data", {})
    metrics_data = [
        ["Market Cap", "EV", "Revenue", "EBITDA", "P/E", "EV/EBITDA"],
        [
            f"${data.get('market_cap', 0) / 1e9:.1f}B" if data.get('market_cap') else "N/D",
            f"${data.get('enterprise_value', 0) / 1e9:.1f}B" if data.get('enterprise_value') else "N/D",
            f"${data.get('revenue', 0) / 1e6:,.0f}M" if data.get('revenue') else "N/D",
            f"${data.get('ebitda', 0) / 1e6:,.0f}M" if data.get('ebitda') else "N/D",
            f"{data.get('pe_trailing', 0):.1f}x" if data.get('pe_trailing') else "N/D",
            f"{data.get('ev_ebitda', 0):.1f}x" if data.get('ev_ebitda') else "N/D",
        ],
    ]

    metrics_table = Table(metrics_data, colWidths=[doc.width/6]*6)
    metrics_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,0), 7),
        ('TEXTCOLOR', (0,0), (-1,0), MUTED),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 10),
        ('TEXTCOLOR', (0,1), (-1,1), INK),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,0), 4),
        ('TOPPADDING', (0,1), (-1,1), 4),
        ('LINEBELOW', (0,0), (-1,0), 0.5, GOLD),
        ('LINEBELOW', (0,1), (-1,1), 0.5, LINE),
    ]))
    story.append(metrics_table)
    story.append(PageBreak())

    # ─── PHASES ───
    phase_names = {
        "fundamentals": ("01", "Análisis de Fundamentos", "10-K DEEP DIVE"),
        "earnings": ("02", "Análisis de Tendencias", "EARNINGS HISTORY"),
        "dcf": ("03", "Proyección Financiera", "DCF FRAMEWORK"),
        "thesis": ("04", "Tesis de Inversión", "EQUITY RESEARCH NOTE"),
    }

    for fase_id in ["fundamentals", "earnings", "dcf", "thesis"]:
        content = cached.get(fase_id)
        if not content:
            continue

        num, title, subtitle = phase_names[fase_id]

        story.append(Paragraph(f"FASE {num}  ·  {subtitle}", styles["phase_subtitle"]))
        story.append(Paragraph(title, styles["phase_title"]))
        story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=12))

        # Parse markdown content into reportlab elements
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Clean markdown bold
            clean = line.replace("**", "").replace("*", "")

            if line.startswith("## "):
                story.append(Paragraph(clean[3:], styles["h2"]))
            elif line.startswith("### "):
                story.append(Paragraph(clean[4:], styles["h3"]))
            elif line.startswith("# "):
                story.append(Paragraph(clean[2:], styles["h2"]))
            elif line.startswith("- ") or line.startswith("• "):
                bullet_text = clean[2:]
                story.append(Paragraph(f"▸ {bullet_text}", styles["bullet"]))
            elif line.startswith("|") and "|" in line[1:]:
                # Skip table rows for now (complex parsing)
                # Render as monospace text
                cells = [c.strip() for c in line.split("|") if c.strip() and c.strip() != "---" and not all(ch in "-:" for ch in c.strip())]
                if cells and not all(c.startswith("-") for c in cells):
                    row_text = "  |  ".join(cells)
                    story.append(Paragraph(row_text, ParagraphStyle(
                        "table_row", fontName="Courier", fontSize=7.5,
                        leading=11, textColor=INK, spaceAfter=1,
                    )))
            else:
                # Bold handling in paragraph
                formatted = line.replace("**", "<b>").replace("**", "</b>")
                story.append(Paragraph(clean, styles["body"]))

        story.append(PageBreak())

    # ─── DISCLAIMER ───
    story.append(Spacer(1, 2*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=8))
    disclaimer = (
        "DISCLAIMER: Este documento fue generado por DealDesk, una herramienta de análisis automatizado. "
        "Los datos provienen de fuentes públicas (Yahoo Finance) y el análisis es generado por inteligencia artificial. "
        "No constituye asesoramiento financiero ni recomendación de inversión. Los usuarios deben realizar su propia "
        "due diligence antes de tomar decisiones de inversión."
    )
    story.append(Paragraph(disclaimer, styles["footer"]))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        f"DealDesk — M&A Intelligence · {datetime.now().strftime('%d/%m/%Y %H:%M')} · Buenos Aires, Argentina",
        styles["footer"]
    ))

    # Build
    doc.build(story)
    buffer.seek(0)

    fecha_str = datetime.now().strftime("%Y%m%d")
    filename = f"Research_{ticker}_{fecha_str}.pdf"

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────
# EXCEL DCF EXPORT
# ─────────────────────────────────────────────

@router.post("/research/excel")
def export_dcf_excel(request: PDFRequest):
    """Genera Excel DCF con fórmulas vivas."""
    from Backend.modules.dcf_excel import generate_dcf_excel

    ticker = request.ticker.upper()
    print(f"\n📊 Excel DCF export → {ticker}")

    try:
        buffer = generate_dcf_excel(ticker)
    except Exception as e:
        raise HTTPException(500, f"Error generando Excel: {str(e)}")

    fecha_str = datetime.now().strftime("%Y%m%d")
    filename = f"DCF_{ticker}_{fecha_str}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

