// ─────────────────────────────────────────────────────────────
//  DEAL INTELLIGENCE UI v2 — DealDesk
//  Renders 3-tier M&A intelligence below comps table
//  Works independently from comps table rows
// ─────────────────────────────────────────────────────────────

let DEAL_INTEL_DATA = {};
let DEAL_INTEL_LOADING = false;

const TIER_CONFIG = {
  STRATEGIC_BUYER: {
    label: "Direct Competitors",
    tier: "Tier 1",
    icon: "🎯",
    color: "#2d6a4f",
    bg: "rgba(45,106,79,0.08)",
    border: "rgba(45,106,79,0.25)",
  },
  ADJACENT_SYNERGY: {
    label: "Strategic Synergies",
    tier: "Tier 2",
    icon: "🔗",
    color: "#4a6fa5",
    bg: "rgba(74,111,165,0.08)",
    border: "rgba(74,111,165,0.25)",
  },
  FINANCIAL_SPONSOR: {
    label: "Financial Sponsors",
    tier: "Tier 3",
    icon: "💰",
    color: "#86BC25",
    bg: "rgba(134,188,37,0.08)",
    border: "rgba(134,188,37,0.25)",
  },
};

const APPROACH_STYLE = {
  PRIORITY: { label: "PRIORITY", bg: "#2d6a4f", color: "#fff" },
  SECONDARY: { label: "SECONDARY", bg: "#86BC25", color: "#fff" },
  MONITOR: { label: "MONITOR", bg: "#999", color: "#fff" },
};

const SIGNAL_STYLE = {
  HIGH: { label: "▲ HIGH", color: "#2d6a4f" },
  MEDIUM: { label: "● MEDIUM", color: "#86BC25" },
  LOW: { label: "▼ LOW", color: "#8b1a1a" },
};

// ── FETCH ──
async function fetchDealIntel(nombre, ticker, industria, revenue, comparables) {
  try {
    const compsClean = (comparables || []).map((c) => ({
      ticker: c.ticker || c.Ticker || "",
      revenue: c.revenue || c["Revenue ($mm)"] || null,
      ev: c.ev || c["EV ($mm)"] || null,
      ebitda: c.ebitda || c["EBITDA ($mm)"] || null,
    }));

    const body = {
      target_name: nombre,
      target_ticker: ticker,
      target_industry: industria,
      target_revenue: revenue,
      comps: compsClean,
    };

    console.log("📤 Deal Intel request:", JSON.stringify(body, null, 2));

    const res = await fetch(`${API}/comps/deal-intel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const text = await res.text();
    console.log("📥 RESPONSE RAW:", text);

    const data = JSON.parse(text);
    return data;
  } catch (e) {
    console.error("❌ fetchDealIntel error:", e);
    throw e;
  }
}

// ── RENDER BRIEF CARD ──
function _renderBriefCard(brief) {
  const approach = APPROACH_STYLE[brief.approach_rec] || APPROACH_STYLE.SECONDARY;
  const signal = SIGNAL_STYLE[brief.expansion_signal] || SIGNAL_STYLE.MEDIUM;

  return `
    <div style="
      background: var(--white, #fff);
      border: 1px solid var(--line, #e5e2dc);
      padding: 16px 20px;
      margin-bottom: 8px;
      transition: all 0.15s;
      cursor: pointer;
    " onmouseenter="this.style.borderColor='var(--gold, #86BC25)';this.style.transform='translateY(-1px)'"
       onmouseleave="this.style.borderColor='var(--line, #e5e2dc)';this.style.transform='none'"
       onclick="this.querySelector('.di-detail').style.display = this.querySelector('.di-detail').style.display === 'none' ? 'block' : 'none'">

      <!-- HEADER ROW -->
      <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
        <span style="
          font-family:'DM Mono',monospace; font-size:12px; font-weight:600;
          color:var(--gold, #86BC25); min-width:60px;
        ">${brief.ticker}</span>

        <span style="
          font-family:'DM Mono',monospace; font-size:9px; letter-spacing:1.5px;
          padding:3px 8px; background:${approach.bg}; color:${approach.color};
        ">${approach.label}</span>

        <span style="
          font-family:'DM Mono',monospace; font-size:10px; color:${signal.color}; font-weight:600;
        ">${signal.label}</span>

        <span style="
          margin-left:auto; font-family:'DM Mono',monospace; font-size:10px; color:var(--muted, #888);
        ">click to expand ▾</span>
      </div>

      <!-- DEAL THESIS (always visible) -->
      <div style="margin-top:10px; font-size:13px; line-height:1.6; color:var(--ink, #111);">
        ${brief.deal_thesis || "Analysis pending..."}
      </div>

      <!-- DETAIL (hidden by default) -->
      <div class="di-detail" style="display:none; margin-top:14px; padding-top:14px; border-top:1px solid var(--line, #e5e2dc);">

        ${brief.strategic_rationale ? `
        <div style="margin-bottom:10px;">
          <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--gold, #86BC25); letter-spacing:1.5px; margin-bottom:4px;">
            STRATEGIC RATIONALE
          </div>
          <div style="font-size:12px; line-height:1.5; color:var(--ink, #111);">
            ${brief.strategic_rationale}
          </div>
        </div>` : ""}

        <div style="margin-bottom:10px;">
          <div style="font-family:'DM Mono',monospace; font-size:9px; color:#8b1a1a; letter-spacing:1.5px; margin-bottom:4px;">
            KEY RISKS
          </div>
          <div style="font-size:12px; line-height:1.5; color:var(--ink, #111);">
            ${brief.risks || "Risk assessment pending."}
          </div>
        </div>

        <div>
          <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--muted, #888); letter-spacing:1.5px; margin-bottom:4px;">
            EXPANSION SIGNAL
          </div>
          <div style="font-size:12px; line-height:1.5; color:var(--ink, #111);">
            ${brief.expansion_note || "No expansion data available."}
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── RENDER ALL 3 TIERS ──
function renderDealIntelSection(briefs) {
  const container = document.getElementById("deal-intel-container");
  if (!container) {
    console.error("❌ #deal-intel-container not found");
    return;
  }

  if (!briefs || briefs.length === 0) {
    container.innerHTML = `
      <div style="padding:20px; text-align:center; color:var(--muted, #888); font-family:'DM Mono',monospace; font-size:12px;">
        Sin resultados de Deal Intelligence
      </div>`;
    container.style.display = "block";
    return;
  }

  const tier1 = briefs.filter((b) => b.tier === "STRATEGIC_BUYER");
  const tier2 = briefs.filter((b) => b.tier === "ADJACENT_SYNERGY");
  const tier3 = briefs.filter((b) => b.tier === "FINANCIAL_SPONSOR");

  const priorities = briefs.filter((b) => b.approach_rec === "PRIORITY").length;
  const source = briefs.length > 0 ? "gemini" : "none";

  let html = `
    <!-- DEAL INTEL HEADER -->
    <div style="
      margin-top:28px; padding:20px 24px;
      background:var(--cream, #faf8f0);
      border:1px solid var(--line, #e5e2dc);
      border-top:2px solid var(--gold, #86BC25);
    ">
      <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;">
        <div>
          <div style="font-family:'DM Mono',monospace; font-size:9px; letter-spacing:3px; color:var(--gold, #86BC25); text-transform:uppercase; margin-bottom:4px;">
            M&A DEAL INTELLIGENCE
          </div>
          <div style="font-family:'Playfair Display',serif; font-size:18px; font-weight:600; color:var(--ink, #111);">
            Strategic Buyer Analysis
          </div>
        </div>
        <div style="display:flex; gap:16px; align-items:center;">
          <div style="text-align:center;">
            <div style="font-family:'DM Mono',monospace; font-size:18px; font-weight:600; color:var(--gold, #86BC25);">${briefs.length}</div>
            <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--muted, #888); letter-spacing:1px;">ANALYZED</div>
          </div>
          <div style="text-align:center;">
            <div style="font-family:'DM Mono',monospace; font-size:18px; font-weight:600; color:#2d6a4f;">${priorities}</div>
            <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--muted, #888); letter-spacing:1px;">PRIORITY</div>
          </div>
          <div style="text-align:center;">
            <div style="font-family:'DM Mono',monospace; font-size:18px; font-weight:600; color:#4a6fa5;">${tier2.length + tier3.length}</div>
            <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--muted, #888); letter-spacing:1px;">SYNERGY+PE</div>
          </div>
        </div>
      </div>
    </div>
  `;

  // Render each tier
  const tiers = [
    { key: "STRATEGIC_BUYER", items: tier1 },
    { key: "ADJACENT_SYNERGY", items: tier2 },
    { key: "FINANCIAL_SPONSOR", items: tier3 },
  ];

  for (const { key, items } of tiers) {
    const cfg = TIER_CONFIG[key];
    if (items.length === 0) continue;

    html += `
      <div style="margin-top:20px;">
        <div style="
          display:flex; align-items:center; gap:10px;
          padding:12px 16px;
          background:${cfg.bg};
          border:1px solid ${cfg.border};
          border-left:3px solid ${cfg.color};
        ">
          <span style="font-size:16px;">${cfg.icon}</span>
          <span style="font-family:'Playfair Display',serif; font-size:14px; font-weight:600; color:var(--ink, #111);">
            ${cfg.tier} — ${cfg.label}
          </span>
          <span style="
            margin-left:auto; font-family:'DM Mono',monospace; font-size:11px;
            color:${cfg.color}; font-weight:600;
          ">${items.length} ${items.length === 1 ? "company" : "companies"}</span>
        </div>

        <div style="margin-top:8px;">
          ${items.map((b) => _renderBriefCard(b)).join("")}
        </div>
      </div>
    `;
  }

  // Source badge
  html += `
    <div style="margin-top:16px; text-align:right;">
      <span style="
        font-family:'DM Mono',monospace; font-size:9px; letter-spacing:1px;
        color:var(--muted, #888);
      ">
        Powered by ${source === "gemini" ? "Google Gemini AI" : "DealDesk Engine"} · ${new Date().toLocaleDateString("es-AR")}
      </span>
    </div>
  `;

  container.innerHTML = html;
  container.style.display = "block";
}

// ── ALSO ADD DOT INDICATORS TO COMPS TABLE ──
function renderDealIntelRows() {
  if (!DEAL_INTEL_DATA || Object.keys(DEAL_INTEL_DATA).length === 0) return;

  const rows = document.querySelectorAll(".comps-table tbody tr");
  rows.forEach((row) => {
    const tickerCell = row.querySelector(".t-ticker");
    if (!tickerCell) return;

    const ticker = tickerCell.textContent.trim().toUpperCase();
    const brief = DEAL_INTEL_DATA[ticker];
    if (!brief) return;

    // Add colored dot to indicate tier
    if (!tickerCell.querySelector(".tier-dot")) {
      const approach = APPROACH_STYLE[brief.approach_rec] || APPROACH_STYLE.SECONDARY;
      const dot = document.createElement("span");
      dot.className = "tier-dot";
      dot.style.cssText = `
        display:inline-block; width:6px; height:6px; border-radius:50%;
        background:${approach.bg}; margin-left:6px; vertical-align:middle;
      `;
      dot.title = `${brief.tier} — ${brief.approach_rec}`;
      tickerCell.appendChild(dot);
    }
  });
}

// ── EXPOSE ──
window.fetchDealIntel = fetchDealIntel;
window.DEAL_INTEL_DATA = DEAL_INTEL_DATA;
window.renderDealIntelSection = renderDealIntelSection;
window.renderDealIntelRows = renderDealIntelRows;