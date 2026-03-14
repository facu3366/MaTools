// ─────────────────────────────────────────────────────────────
//  HERRAMIENTA DCF & WACC — DealDesk
//  Autocomplete live via Yahoo Finance (proxied por backend propio)
//  Patrón idéntico a herramienta-comparables.js
// ─────────────────────────────────────────────────────────────



let dcfSelectedSuggestion = -1;
let dcfSearchTimeout      = null;
let dcfSelectedTicker     = null;



// ─────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────
function fmt(v, d = 1) {
  return v == null
    ? "—"
    : typeof v === "number"
    ? v.toLocaleString("es-AR", { maximumFractionDigits: d })
    : v;
}

function spinner(txt = "CONSULTANDO...") {
  return `<div class="result-box"><div class="spinner-wrap"><div class="spinner"></div><div class="spinner-text">${txt}</div></div></div>`;
}

function getBancoType(n) {
  n = n || "";
  if (/NACION|PROVINCIA|CIUDAD|PROV /.test(n)) return "PÚBLICO";
  if (/DIGITAL|NARANJA|UALA/.test(n)) return "DIGITAL";
  return "PRIVADO";
}

// ─────────────────────────────────────────────
// AUTOCOMPLETE — idéntico a Comps
// ─────────────────────────────────────────────

async function dcfSearchEmpresas(query) {
  if (!query || query.length < 2) return [];
  try {
    const res  = await fetch(`${API}/yf/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    return (data.quotes || [])
      .filter(q => ["EQUITY", "ETF"].includes(q.quoteType))
      .map(q => ({
        ticker:   q.symbol,
        name:     q.longname || q.shortname || q.symbol,
        exchange: q.exchDisp || q.exchange || "",
      }));
  } catch (err) {
    console.error("Yahoo Finance search error:", err);
    return [];
  }
}

function dcfShowSuggestions(val) {
  const box = document.getElementById("dcf-suggestions");
  dcfSelectedSuggestion = -1;
  clearTimeout(dcfSearchTimeout);

  if (!val || val.length < 2) {
    box.style.display = "none";
    return;
  }

  box.innerHTML = `<div class="suggestion-loading">Buscando...</div>`;
  box.style.display = "block";

  dcfSearchTimeout = setTimeout(async () => {
    const results = await dcfSearchEmpresas(val);

    if (!results.length) {
      box.innerHTML = `<div class="suggestion-empty">Sin resultados para "<em>${val}</em>"</div>`;
      return;
    }

    box.innerHTML = results.map((e, i) => `
      <div class="suggestion-item" data-index="${i}"
           onmousedown="dcfSelectSuggestion('${e.ticker}', '${e.name.replace(/'/g, "\\'")}')"
           onmouseover="dcfHighlightSuggestion(${i})">
        <span class="sug-ticker">${e.ticker}</span>
        <span class="sug-name">${e.name}</span>
        <span class="sug-exchange">${e.exchange}</span>
      </div>
    `).join("");

    box.style.display = "block";
  }, 300);
}

function dcfHighlightSuggestion(index) {
  document.querySelectorAll("#dcf-suggestions .suggestion-item").forEach((el, i) => {
    el.classList.toggle("active", i === index);
  });
  dcfSelectedSuggestion = index;
}

function dcfHandleKey(e) {
  const items = document.querySelectorAll("#dcf-suggestions .suggestion-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    dcfSelectedSuggestion = Math.min(dcfSelectedSuggestion + 1, items.length - 1);
    dcfHighlightSuggestion(dcfSelectedSuggestion);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    dcfSelectedSuggestion = Math.max(dcfSelectedSuggestion - 1, 0);
    dcfHighlightSuggestion(dcfSelectedSuggestion);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (dcfSelectedSuggestion >= 0) {
      const items2 = document.querySelectorAll("#dcf-suggestions .suggestion-item");
      if (items2[dcfSelectedSuggestion]) {
        items2[dcfSelectedSuggestion].dispatchEvent(new Event("mousedown"));
      }
    }
  } else if (e.key === "Escape") {
    document.getElementById("dcf-suggestions").style.display = "none";
  }
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#dcf-empresa") && !e.target.closest("#dcf-suggestions")) {
    const box = document.getElementById("dcf-suggestions");
    if (box) box.style.display = "none";
  }
});

// ─────────────────────────────────────────────
// SELECCIÓN
// ─────────────────────────────────────────────

async function dcfSelectSuggestion(ticker, name) {
  dcfSelectedTicker = ticker;
  document.getElementById("dcf-empresa").value = `${name} (${ticker})`;
  document.getElementById("dcf-suggestions").style.display = "none";

  await dcfFetchRevenueCard(ticker, name);
}

// ─────────────────────────────────────────────
// REVENUE CARD — idéntica a Comps
// ─────────────────────────────────────────────

async function dcfFetchRevenueCard(ticker, name) {
  const container = document.getElementById("dcf-revenue-preview");
  if (!container) return;

  container.innerHTML = `<div class="rev-loading">Cargando datos financieros…</div>`;
  container.style.display = "block";

  try {
    const res   = await fetch(`${API}/yf/${ticker}`);
    const data  = await res.json();
    const fin   = data?.quoteSummary?.result?.[0]?.financialData;
    const stats = data?.quoteSummary?.result?.[0]?.defaultKeyStatistics;

    if (!fin) {
      container.innerHTML = `<div class="rev-error">No se encontraron datos financieros para <strong>${ticker}</strong>.</div>`;
      return;
    }

    const revenue   = fin.totalRevenue?.raw;
    const ebitda    = fin.ebitda?.raw;
    const netIncome = fin.netIncomeToCommon?.raw;
    const ebitdaMgn = fin.ebitdaMargins?.raw;
    const profitMgn = fin.profitMargins?.raw;
    const ev        = stats?.enterpriseValue?.raw;

    const fmtVal = (val) => {
      if (val == null) return "—";
      const mm = val / 1e6;
      return Math.abs(mm) >= 1000 ? `${(mm / 1000).toFixed(1)}B` : `${mm.toFixed(0)}M`;
    };
    const pct = (val) => val != null ? `${(val * 100).toFixed(1)}%` : "—";

    container.innerHTML = `
      <div class="rev-card">
        <div class="rev-card-header">
          <div class="rev-company">
            <span class="rev-ticker-badge">${ticker}</span>
            <span class="rev-name-text">${name}</span>
          </div>
          <div class="rev-source">
            Fuente: <a href="https://finance.yahoo.com/quote/${ticker}/financials/" target="_blank" rel="noopener">Yahoo Finance</a>
            &nbsp;·&nbsp; TTM (Trailing Twelve Months)
          </div>
        </div>
        <div class="rev-grid">
          <div class="rev-metric rev-metric--main">
            <div class="rev-metric-label">Revenue</div>
            <div class="rev-metric-value">${fmtVal(revenue)}</div>
            <div class="rev-metric-sub">USD</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">EBITDA</div>
            <div class="rev-metric-value">${fmtVal(ebitda)}</div>
            <div class="rev-metric-sub">${pct(ebitdaMgn)} margen</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Net Income</div>
            <div class="rev-metric-value">${fmtVal(netIncome)}</div>
            <div class="rev-metric-sub">${pct(profitMgn)} margen</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Enterprise Value</div>
            <div class="rev-metric-value">${fmtVal(ev)}</div>
            <div class="rev-metric-sub">USD</div>
          </div>
        </div>
        <div class="rev-auto-note">
          ↑ Datos pre-cargados. Ajustá RFR y ERP si es necesario.
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="rev-error">Error al cargar datos: ${err.message}</div>`;
    console.error("dcfFetchRevenueCard error:", err);
  }
}

// ─────────────────────────────────────────────
// RUN DCF
// ─────────────────────────────────────────────

async function runDCF() {
  const ticker = dcfSelectedTicker
    || document.getElementById("dcf-empresa").value.split("(").pop().replace(")", "").trim().toUpperCase();

  if (!ticker) {
    alert("Ingresá o seleccioná una empresa");
    return;
  }

  const btn = document.getElementById("btn-dcf");
  document.getElementById("result-dcf").innerHTML = spinner("DESCARGANDO FINANCIALS...");
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/financials`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker,
        incluir_wacc:        document.getElementById("dcf-wacc").value === "true",
        risk_free_rate:      parseFloat(document.getElementById("dcf-rfr").value)  || 4.5,
        equity_risk_premium: parseFloat(document.getElementById("dcf-erp").value)  || 5.5,
      }),
    });

    const data = await res.json();
    const f = data.financials || {};
    const w = data.wacc || {};

    document.getElementById("result-dcf").innerHTML = `
      <div class="result-box">
        <div class="result-header">
          <div class="result-title">${f.empresa || ticker} (${ticker})</div>
          <div class="result-date">${new Date().toLocaleDateString("es-AR")}</div>
        </div>
        <div class="result-body">
          <div class="fin-grid">
            <div class="fin-card">
              <div class="fin-card-label">Revenue</div>
              <div class="fin-card-value">$${fmt(f.revenue_mm)}</div>
              <div class="fin-card-sub">USD mm</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">EBITDA Margin</div>
              <div class="fin-card-value">${fmt(f.ebitda_margin_pct)}%</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">FCF</div>
              <div class="fin-card-value">$${fmt(f.fcf_mm)}</div>
              <div class="fin-card-sub">USD mm</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">Beta</div>
              <div class="fin-card-value">${fmt(f.beta)}</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">Net Debt / EBITDA</div>
              <div class="fin-card-value">${fmt(f.net_debt_ebitda)}x</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">WACC</div>
              <div class="fin-card-value">${w.wacc_pct ? w.wacc_pct + "%" : "—"}</div>
            </div>
          </div>
        </div>
      </div>`;
  } catch (e) {
    document.getElementById("result-dcf").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}

// ─────────────────────────────────────────────
// PRECEDENTS
// ─────────────────────────────────────────────
async function runPrecedents() {
  const btn = document.getElementById("btn-prec");
  document.getElementById("result-prec").innerHTML = spinner("BUSCANDO DEALS...");
  btn.disabled = true;

  try {
    const evMin = document.getElementById("prec-ev-min").value;
    const body = {
      sector: document.getElementById("prec-sector").value,
      region: document.getElementById("prec-region").value,
      años:   parseInt(document.getElementById("prec-years").value),
    };
    if (evMin) body.min_ev_mm = parseFloat(evMin);

    const res = await fetch(`${API}/precedents`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });

    const d     = await res.json();
    const deals = d.deals || [];
    const s     = d.estadisticas || {};

    document.getElementById("result-prec").innerHTML = `
      <div class="result-box">
        <div class="result-header">
          <div class="result-title">Precedentes — ${body.sector} · ${body.region}</div>
          <div class="result-date">${d.periodo || ""}</div>
        </div>
        <div class="result-body">
          <div class="fin-grid">
            <div class="fin-card">
              <div class="fin-card-label">Deals</div>
              <div class="fin-card-value">${s.n_deals || deals.length}</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">EV Mediana</div>
              <div class="fin-card-value">${s.ev_mediana_mm ? "$" + fmt(s.ev_mediana_mm) + "mm" : "—"}</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">EV/EBITDA Med.</div>
              <div class="fin-card-value">${s.ev_ebitda_mediana ? fmt(s.ev_ebitda_mediana) + "x" : "—"}</div>
            </div>
          </div>
        </div>
      </div>`;
  } catch (e) {
    document.getElementById("result-prec").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}

// ─────────────────────────────────────────────
// BCRA
// ─────────────────────────────────────────────
let bcraData = null;

async function runBCRA() {
  const btn = document.getElementById("btn-bcra");
  document.getElementById("result-bcra").innerHTML = spinner("SCRAPEANDO BCRA...");
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/bcra/bancos`);
    bcraData = await res.json();
    renderBCRA(bcraData, "Activos");
  } catch (e) {
    document.getElementById("result-bcra").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}
