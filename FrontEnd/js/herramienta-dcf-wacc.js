// ─────────────────────────────────────────────────────────────
//  HERRAMIENTA DCF & WACC — DealDesk
//  Autocomplete live via Yahoo Finance (proxied por backend propio)
//
//  DEPENDENCIAS: utilidades-ui.js (API, fmt, spinner) debe cargarse antes.
//  NO redefinir fmt(), spinner(), getBancoType() — ya existen en utilidades-ui.js
// ─────────────────────────────────────────────────────────────

let dcfSelectedSuggestion = -1;
let dcfSearchTimeout = null;
let dcfSelectedTicker = null;

// ─────────────────────────────────────────────
// AUTOCOMPLETE
// ─────────────────────────────────────────────

async function dcfSearchEmpresas(query) {
  if (!query || query.length < 2) return [];
  try {
    const res = await fetch(`${API}/yf/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    return (data.quotes || [])
      .filter((q) => ["EQUITY", "ETF"].includes(q.quoteType))
      .map((q) => ({
        ticker: q.symbol,
        name: q.longname || q.shortname || q.symbol,
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

    box.innerHTML = results
      .map(
        (e, i) => `
      <div class="suggestion-item" data-index="${i}"
           onmousedown="dcfSelectSuggestion('${e.ticker}', '${e.name.replace(/'/g, "\\'")}')"
           onmouseover="dcfHighlightSuggestion(${i})">
        <span class="sug-ticker">${e.ticker}</span>
        <span class="sug-name">${e.name}</span>
        <span class="sug-exchange">${e.exchange}</span>
      </div>
    `,
      )
      .join("");

    box.style.display = "block";
  }, 300);
}

function dcfHighlightSuggestion(index) {
  document
    .querySelectorAll("#dcf-suggestions .suggestion-item")
    .forEach((el, i) => {
      el.classList.toggle("active", i === index);
    });
  dcfSelectedSuggestion = index;
}

function dcfHandleKey(e) {
  const items = document.querySelectorAll("#dcf-suggestions .suggestion-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    dcfSelectedSuggestion = Math.min(
      dcfSelectedSuggestion + 1,
      items.length - 1,
    );
    dcfHighlightSuggestion(dcfSelectedSuggestion);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    dcfSelectedSuggestion = Math.max(dcfSelectedSuggestion - 1, 0);
    dcfHighlightSuggestion(dcfSelectedSuggestion);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (dcfSelectedSuggestion >= 0) {
      const items2 = document.querySelectorAll(
        "#dcf-suggestions .suggestion-item",
      );
      if (items2[dcfSelectedSuggestion]) {
        items2[dcfSelectedSuggestion].dispatchEvent(new Event("mousedown"));
      }
    }
  } else if (e.key === "Escape") {
    document.getElementById("dcf-suggestions").style.display = "none";
  }
}

document.addEventListener("click", (e) => {
  if (
    !e.target.closest("#dcf-empresa") &&
    !e.target.closest("#dcf-suggestions")
  ) {
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
// REVENUE CARD — usa /yf/{ticker} que devuelve campos planos:
//   { revenue, ebitda, marketCap, enterpriseValue, price, ... }
// ─────────────────────────────────────────────

async function dcfFetchRevenueCard(ticker, name) {
  const container = document.getElementById("dcf-revenue-preview");
  if (!container) return;

  container.innerHTML = `<div class="rev-loading">Cargando datos financieros…</div>`;
  container.style.display = "block";

  try {
    const res = await fetch(`${API}/yf/${ticker}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // /yf/{ticker} devuelve campos planos — NO quoteSummary
    const revenue = data.revenue;
    const ebitda = data.ebitda;
    const ev = data.enterpriseValue;
    const marketCap = data.marketCap;
    const price = data.price;

    const fmtVal = (val) => {
      if (val == null) return "—";
      const mm = val / 1e6;
      return Math.abs(mm) >= 1000
        ? `$${(mm / 1000).toFixed(1)}B`
        : `$${mm.toFixed(0)}M`;
    };

    const ebitdaMargin =
      revenue && ebitda ? ((ebitda / revenue) * 100).toFixed(1) + "%" : "—";

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
            <div class="rev-metric-sub">${ebitdaMargin} margen</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Enterprise Value</div>
            <div class="rev-metric-value">${fmtVal(ev)}</div>
            <div class="rev-metric-sub">USD</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Market Cap</div>
            <div class="rev-metric-value">${fmtVal(marketCap)}</div>
            <div class="rev-metric-sub">USD</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Price</div>
            <div class="rev-metric-value">$${price ?? "—"}</div>
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
  const ticker =
    dcfSelectedTicker ||
    document
      .getElementById("dcf-empresa")
      .value.split("(")
      .pop()
      .replace(")", "")
      .trim()
      .toUpperCase();

  if (!ticker) {
    alert("Ingresá o seleccioná una empresa");
    return;
  }

  const btn = document.getElementById("btn-dcf");
  document.getElementById("result-dcf").innerHTML = spinner(
    "DESCARGANDO FINANCIALS...",
  );
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/financials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker,
        incluir_wacc: document.getElementById("dcf-wacc").value === "true",
        risk_free_rate:
          parseFloat(document.getElementById("dcf-rfr").value) || 4.5,
        equity_risk_premium:
          parseFloat(document.getElementById("dcf-erp").value) || 5.5,
      }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

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
