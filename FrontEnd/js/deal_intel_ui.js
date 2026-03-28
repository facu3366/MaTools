// ─────────────────────────────────────────────────────────────
//  DEAL INTELLIGENCE UI — inject into herramienta-comparables.js
//
//  Add this code at the END of herramienta-comparables.js
//  It hooks into the existing comps flow and adds expandable deal briefs
// ─────────────────────────────────────────────────────────────

// ── DEAL INTEL STATE ──
let DEAL_INTEL_DATA = {}; // ticker → brief
let DEAL_INTEL_LOADING = false;

// ── TIER BADGES ──
const TIER_CONFIG = {
  STRATEGIC_BUYER: {
    label: "STRATEGIC",
    color: "#2d6a4f",
    bg: "rgba(45,106,79,0.1)",
  },
  FINANCIAL_SPONSOR: {
    label: "FINANCIAL",
    color: "#86BC25",
    bg: "rgba(134,188,37,0.1)",
  },
  ADJACENT_SYNERGY: {
    label: "SYNERGY",
    color: "#4a6fa5",
    bg: "rgba(74,111,165,0.1)",
  },
};

const APPROACH_CONFIG = {
  PRIORITY: { label: "PRIORITY", color: "#fff", bg: "#2d6a4f" },
  SECONDARY: { label: "SECONDARY", color: "#fff", bg: "#86BC25" },
  MONITOR: { label: "MONITOR", color: "#fff", bg: "#999" },
};

const SIGNAL_CONFIG = {
  HIGH: { label: "▲ HIGH", color: "#2d6a4f" },
  MEDIUM: { label: "● MEDIUM", color: "#86BC25" },
  LOW: { label: "▼ LOW", color: "#8b1a1a" },
};

// ── FETCH DEAL INTELLIGENCE (called after comps load) ──
async function fetchDealIntel(nombre, ticker, industria, revenue, comparables) {
  try {
    // limpio comparables por si viene algo raro
    const compsClean = (comparables || []).map((c) => {
      return {
        ticker: c.ticker || "",
        revenue: c.revenue || null,
        ev: c.ev || null,
        ebitda: c.ebitda || null,
      };
    });

    const body = {
      target_name: nombre,
      target_ticker: ticker,
      target_industry: industria,
      target_revenue: revenue,
      comps: compsClean,
    };
    // debug clave
    console.log("📤 BODY QUE SE ENVÍA:");
    console.log(JSON.stringify(body, null, 2));

    const res = await fetch(`${API}/comps/deal-intel`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    const text = await res.text();

    // debug respuesta cruda
    console.log("📥 RESPONSE RAW:");
    console.log(text);

    const data = JSON.parse(text);

    return data;
  } catch (e) {
    console.error("❌ ERROR EN fetchDealIntel:", e);
    throw e;
  }
}
// ── RENDER EXPANDABLE DEAL BRIEF ROWS ──
function renderDealIntelRows() {
  const rows = document.querySelectorAll(".comps-table tbody tr");

  // Remove any existing brief rows
  document.querySelectorAll(".deal-intel-row").forEach((r) => r.remove());

  rows.forEach((row) => {
    const tickerCell = row.querySelector(".t-ticker");
    if (!tickerCell) return;

    const ticker = tickerCell.textContent.trim();
    const brief = DEAL_INTEL_DATA[ticker];
    if (!brief) return;

    // Add click handler to toggle
    row.style.cursor = "pointer";
    row.onclick = () => toggleDealBrief(ticker, row);

    // Add tier badge to ticker cell
    const tierCfg = TIER_CONFIG[brief.tier] || TIER_CONFIG["STRATEGIC_BUYER"];
    const approachCfg =
      APPROACH_CONFIG[brief.approach_rec] || APPROACH_CONFIG["SECONDARY"];

    if (!tickerCell.querySelector(".tier-dot")) {
      const dot = document.createElement("span");
      dot.className = "tier-dot";
      dot.style.cssText = `
                display:inline-block; width:6px; height:6px; border-radius:50%;
                background:${approachCfg.bg}; margin-left:6px; vertical-align:middle;
            `;
      dot.title = `${brief.approach_rec} — click to expand`;
      tickerCell.appendChild(dot);
    }
  });
}

// ── TOGGLE DEAL BRIEF ──
function toggleDealBrief(ticker, row) {
  const existingBrief = row.nextElementSibling;
  if (existingBrief && existingBrief.classList.contains("deal-intel-row")) {
    existingBrief.remove();
    return;
  }

  // Remove any other open briefs
  document.querySelectorAll(".deal-intel-row").forEach((r) => r.remove());

  const brief = DEAL_INTEL_DATA[ticker];
  if (!brief) return;

  const tierCfg = TIER_CONFIG[brief.tier] || TIER_CONFIG["STRATEGIC_BUYER"];
  const approachCfg =
    APPROACH_CONFIG[brief.approach_rec] || APPROACH_CONFIG["SECONDARY"];
  const signalCfg =
    SIGNAL_CONFIG[brief.expansion_signal] || SIGNAL_CONFIG["MEDIUM"];

  const colSpan = row.children.length;
  const briefRow = document.createElement("tr");
  briefRow.className = "deal-intel-row";
  briefRow.innerHTML = `
        <td colspan="${colSpan}" style="
            padding:0; border-bottom:2px solid ${tierCfg.color};
            background: ${tierCfg.bg};
        ">
            <div style="padding:16px 20px;">
                
                <!-- HEADER: Tier + Approach + Signal -->
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px; flex-wrap:wrap;">
                    <span style="
                        font-family:'DM Mono',monospace; font-size:9px; letter-spacing:2px;
                        padding:3px 10px; background:${tierCfg.bg}; color:${tierCfg.color};
                        border:1px solid ${tierCfg.color};
                    ">${tierCfg.label}</span>
                    
                    <span style="
                        font-family:'DM Mono',monospace; font-size:9px; letter-spacing:2px;
                        padding:3px 10px; background:${approachCfg.bg}; color:${approachCfg.color};
                    ">${approachCfg.label}</span>
                    
                    <span style="
                        font-family:'DM Mono',monospace; font-size:10px;
                        color:${signalCfg.color}; font-weight:600;
                    ">${signalCfg.label}</span>
                    
                    <span style="
                        font-family:'DM Mono',monospace; font-size:10px;
                        color:var(--muted); margin-left:auto;
                    ">DEAL INTELLIGENCE · ${ticker}</span>
                </div>

                <!-- DEAL THESIS -->
                <div style="margin-bottom:10px;">
                    <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--muted); letter-spacing:1.5px; margin-bottom:4px;">
                        DEAL THESIS
                    </div>
                    <div style="font-size:13px; line-height:1.6; color:var(--ink);">
                        ${brief.deal_thesis || "No thesis available"}
                    </div>
                </div>

                <!-- RISKS -->
                <div style="margin-bottom:10px;">
                    <div style="font-family:'DM Mono',monospace; font-size:9px; color:#8b1a1a; letter-spacing:1.5px; margin-bottom:4px;">
                        RISKS
                    </div>
                    <div style="font-size:12px; line-height:1.5; color:var(--ink);">
                        ${brief.risks || "No risks identified"}
                    </div>
                </div>

                <!-- EXPANSION -->
                <div>
                    <div style="font-family:'DM Mono',monospace; font-size:9px; color:var(--muted); letter-spacing:1.5px; margin-bottom:4px;">
                        EXPANSION SIGNAL
                    </div>
                    <div style="font-size:12px; line-height:1.5; color:var(--ink);">
                        ${brief.expansion_note || "No expansion data"}
                    </div>
                </div>

            </div>
        </td>
    `;

  row.after(briefRow);
}

// ── EXPOSE GLOBALLY ──
window.fetchDealIntel = fetchDealIntel;
window.DEAL_INTEL_DATA = DEAL_INTEL_DATA;
