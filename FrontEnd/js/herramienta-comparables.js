// ─────────────────────────────────────────────────────────────
//  HERRAMIENTA COMPARABLES — DealDesk
//  Autocomplete live via Yahoo Finance Search API
// ─────────────────────────────────────────────────────────────

let selectedSuggestion = -1;
let searchTimeout      = null;
let selectedTicker     = null;

// ── PROXY HELPER ──────────────────────────────────────────────
// corsproxy.io  → funciona bien para el search (GET simple)
// allorigins    → funciona para quoteSummary (responde JSON wrapped)

async function fetchYF(url, useAllOrigins = false) {
  if (useAllOrigins) {
    const wrapped = `https://api.allorigins.win/get?url=${encodeURIComponent(url)}`;
    const res     = await fetch(wrapped);
    const json    = await res.json();
    return JSON.parse(json.contents);
  } else {
    const proxied = `https://corsproxy.io/?url=${encodeURIComponent(url)}`;
    const res     = await fetch(proxied);
    return res.json();
  }
}

// ── AUTOCOMPLETE ──────────────────────────────────────────────

async function searchEmpresas(query) {
  if (!query || query.length < 2) return [];

  try {
    const url  = `https://query2.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(query)}&quotesCount=8&newsCount=0&listsCount=0`;
    const data = await fetchYF(url, false);

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

function showSuggestions(val) {
  const box = document.getElementById("suggestions");
  selectedSuggestion = -1;
  clearTimeout(searchTimeout);

  if (!val || val.length < 2) {
    box.style.display = "none";
    return;
  }

  box.innerHTML = `<div class="suggestion-loading">Buscando...</div>`;
  box.style.display = "block";

  searchTimeout = setTimeout(async () => {
    const results = await searchEmpresas(val);

    if (!results.length) {
      box.innerHTML = `<div class="suggestion-empty">Sin resultados para "<em>${val}</em>"</div>`;
      return;
    }

    box.innerHTML = results.map((e, i) => `
      <div class="suggestion-item" data-index="${i}"
           onmousedown="selectSuggestion('${e.ticker}', '${e.name.replace(/'/g, "\\'")}')"
           onmouseover="highlightSuggestion(${i})">
        <span class="sug-ticker">${e.ticker}</span>
        <span class="sug-name">${e.name}</span>
        <span class="sug-exchange">${e.exchange}</span>
      </div>
    `).join("");

    box.style.display = "block";
  }, 300);
}

function highlightSuggestion(index) {
  document.querySelectorAll(".suggestion-item").forEach((el, i) => {
    el.classList.toggle("active", i === index);
  });
  selectedSuggestion = index;
}

function handleKey(e) {
  const items = document.querySelectorAll(".suggestion-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    selectedSuggestion = Math.min(selectedSuggestion + 1, items.length - 1);
    highlightSuggestion(selectedSuggestion);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    selectedSuggestion = Math.max(selectedSuggestion - 1, 0);
    highlightSuggestion(selectedSuggestion);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (selectedSuggestion >= 0 && items[selectedSuggestion]) {
      items[selectedSuggestion].dispatchEvent(new Event("mousedown"));
    }
  } else if (e.key === "Escape") {
    document.getElementById("suggestions").style.display = "none";
  }
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#comps-empresa") && !e.target.closest("#suggestions")) {
    document.getElementById("suggestions").style.display = "none";
  }
});

// ── SELECCIÓN ─────────────────────────────────────────────────

async function selectSuggestion(ticker, name) {
  selectedTicker = ticker;
  document.getElementById("comps-empresa").value = `${name} (${ticker})`;
  document.getElementById("suggestions").style.display = "none";

  // Corren en paralelo para ser más rápido
  await Promise.all([
    autoDetectSector(ticker),
    fetchRevenueCard(ticker, name),
  ]);
}

// ── AUTO-DETECT SECTOR ────────────────────────────────────────

async function autoDetectSector(ticker) {
  const hint = document.getElementById("detect-hint");
  if (!ticker) return;

  try {
    const url     = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${ticker}?modules=assetProfile`;
    const data    = await fetchYF(url, true);
    const profile = data?.quoteSummary?.result?.[0]?.assetProfile;

    if (!profile?.sector) return;

    const sectorMap = {
      "Technology":             "Technology",
      "Financial Services":     "Financials",
      "Healthcare":             "Health Insurance",
      "Energy":                 "Energy",
      "Consumer Cyclical":      "Consumer",
      "Consumer Defensive":     "Consumer",
      "Real Estate":            "Real Estate",
      "Industrials":            "Industrials",
      "Basic Materials":        "Industrials",
      "Communication Services": "Technology",
      "Utilities":              "Industrials",
    };

    const mapped = sectorMap[profile.sector] || profile.sector;
    const sel    = document.getElementById("comps-sector");
    let found    = false;

    for (let opt of sel.options) {
      if (opt.value === mapped) { sel.value = mapped; found = true; break; }
    }
    if (!found) {
      sel.add(new Option(mapped, mapped, true, true));
    }

    hint.textContent = `✓ Sector detectado: ${profile.sector}`;
    hint.style.color = "var(--gold)";
  } catch (err) {
    console.error("autoDetectSector error:", err);
  }
}

// ── REVENUE CARD ──────────────────────────────────────────────

async function fetchRevenueCard(ticker, name) {
  const container = document.getElementById("revenue-preview");
  if (!container) return;

  container.innerHTML = `<div class="rev-loading">Cargando datos financieros…</div>`;
  container.style.display = "block";

  try {
    const url   = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${ticker}?modules=financialData,defaultKeyStatistics`;
    const data  = await fetchYF(url, true);
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

    if (revenue != null) {
      document.getElementById("comps-revenue").value = Math.round(revenue / 1e6);
    }

    const fmt = (val) => {
      if (val == null) return "—";
      const mm = val / 1e6;
      return Math.abs(mm) >= 1000
        ? `${(mm / 1000).toFixed(1)}B`
        : `${mm.toFixed(0)}M`;
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
            <div class="rev-metric-value">${fmt(revenue)}</div>
            <div class="rev-metric-sub">USD</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">EBITDA</div>
            <div class="rev-metric-value">${fmt(ebitda)}</div>
            <div class="rev-metric-sub">${pct(ebitdaMgn)} margen</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Net Income</div>
            <div class="rev-metric-value">${fmt(netIncome)}</div>
            <div class="rev-metric-sub">${pct(profitMgn)} margen</div>
          </div>
          <div class="rev-metric">
            <div class="rev-metric-label">Enterprise Value</div>
            <div class="rev-metric-value">${fmt(ev)}</div>
            <div class="rev-metric-sub">USD</div>
          </div>
        </div>
        <div class="rev-auto-note">
          ↑ Revenue pre-cargado en el campo. Podés editarlo manualmente.
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="rev-error">Error al cargar datos: ${err.message}</div>`;
    console.error("fetchRevenueCard error:", err);
  }
}

// ── GENERAR COMPS ─────────────────────────────────────────────

async function runComps() {
  const rawEmpresa = document.getElementById("comps-empresa").value || "Target";
  const empresa    = selectedTicker || rawEmpresa;
  const revenue    = parseFloat(document.getElementById("comps-revenue").value) || 1000;
  const sector     = document.getElementById("comps-sector").value;
  const analista   = document.getElementById("comps-analista").value || "Analista";
  const escala     = document.getElementById("comps-escala")?.value  || "mm";
  const moneda     = document.getElementById("comps-moneda")?.value  || "USD";
  const rangoMin   = parseFloat(document.getElementById("comps-rango-min")?.value) || 30;
  const rangoMax   = parseFloat(document.getElementById("comps-rango-max")?.value) || 300;

  const btn = document.getElementById("btn-comps");
  document.getElementById("result-comps").innerHTML = spinner("DESCARGANDO COMPS...");
  btn.disabled = true;

  try {
    const res = await fetch(`${API}/comps`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mensaje:          `Dame comps de ${empresa}`,
        analista,
        empresa_override: empresa,
        sector_override:  sector,
        revenue_override: revenue,
        moneda,
        escala,
        rango_min_pct:    rangoMin,
        rango_max_pct:    rangoMax,
      }),
    });

    const d = await res.json();

    if (!res.ok || d.detail) {
      document.getElementById("result-comps").innerHTML =
        `<div class="error-msg">Error API: ${d.detail || JSON.stringify(d)}</div>`;
      btn.disabled = false;
      return;
    }

    document.getElementById("result-comps").innerHTML = `
      <div class="result-box">
        <div class="result-header">
          <div class="result-title">Comps — ${d.empresa_target || empresa}</div>
          <div class="result-date">${new Date().toLocaleDateString("es-AR")}</div>
        </div>
        <div class="result-body">
          <div class="fin-grid">
            <div class="fin-card">
              <div class="fin-card-label">Sector</div>
              <div class="fin-card-value">${d.sector}</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">Universe</div>
              <div class="fin-card-value">${d.n_empresas_universe}</div>
            </div>
            <div class="fin-card">
              <div class="fin-card-label">Comparables</div>
              <div class="fin-card-value">${d.n_empresas_filtradas}</div>
            </div>
          </div>
          <p style="font-size:13px;color:var(--muted)">${d.mensaje}</p>
        </div>
      </div>
    `;
  } catch (e) {
    document.getElementById("result-comps").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}
