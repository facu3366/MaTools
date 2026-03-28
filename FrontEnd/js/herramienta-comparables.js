// ─────────────────────────────────────────────────────────────
//  HERRAMIENTA COMPARABLES v5 — DealDesk
//  Autocomplete HÍBRIDO: /api/empresas (backend) + Yahoo fallback
//  TTM Revenue + Pre-calculated multiples from backend
// ─────────────────────────────────────────────────────────────

// API ya está declarada en utilidades-ui.js (se carga antes en index.html)
// NO re-declarar const API acá — causa SyntaxError y mata todo el JS

let selectedSuggestion = -1;
let searchTimeout = null;
let selectedTicker = null;

// ── CARGA DEL CATÁLOGO DE EMPRESAS ───────────────────────────
let EMPRESA_LIST = [];
let empresasLoaded = false;

let CURRENT_COMPS_DATA = null;
let CURRENT_VIEW = "filtradas"; // default

async function loadEmpresas() {
  // Intento 1: endpoint del backend (funciona siempre en Railway)
  try {
    const resAPI = await fetch(`${API}/api/empresas`);
    if (resAPI.ok) {
      EMPRESA_LIST = await resAPI.json();
      empresasLoaded = true;
      console.log(`✅ Empresas cargadas desde API: ${EMPRESA_LIST.length}`);
      return;
    }
  } catch (err) {
    console.warn("⚠️ /api/empresas falló:", err.message);
  }

  // Intento 2: archivo local (solo si abrís index.html directo)
  try {
    const resBack = await fetch("Data/empresas.json");
    if (resBack.ok) {
      EMPRESA_LIST = await resBack.json();
      empresasLoaded = true;
      console.log(
        `✅ Empresas cargadas desde JSON local: ${EMPRESA_LIST.length}`,
      );
      return;
    }
  } catch (err) {
    console.warn("⚠️ Data/empresas.json no encontrado");
  }

  console.error("❌ No se pudo cargar el catálogo de empresas");
}

loadEmpresas();

// ── BÚSQUEDA HÍBRIDA ─────────────────────────────────────────

function searchLocal(query) {
  if (!empresasLoaded || !query || query.length < 2) return [];
  const q = query.toLowerCase().trim();
  return EMPRESA_LIST.filter(
    (e) =>
      (e.name && e.name.toLowerCase().includes(q)) ||
      (e.ticker && e.ticker.toLowerCase().includes(q)) ||
      (e.alias || []).some((a) => a.toLowerCase().includes(q)),
  )
    .slice(0, 8)
    .map((e) => ({
      ticker: e.ticker,
      name: e.name,
      sector: e.sector || "",
      exchange: "",
      source: "local",
    }));
}

async function searchBackend(query) {
  try {
    const res = await fetch(`${API}/yf/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) return [];
    const data = await res.json();
    const quotes = data.quotes || [];
    return quotes
      .filter((q) => q.quoteType === "EQUITY" || q.typeDisp === "Equity")
      .slice(0, 8)
      .map((q) => ({
        ticker: q.symbol,
        name: q.shortname || q.longname || q.symbol,
        sector: q.sector || "",
        exchange: q.exchange || q.exchDisp || "",
        source: "yahoo",
      }));
  } catch (err) {
    return [];
  }
}

async function searchEmpresas(query) {
  if (!query || query.length < 2) return [];
  const local = searchLocal(query);
  if (local.length >= 3) return local;
  const remote = await searchBackend(query);
  const seen = new Set(local.map((r) => r.ticker));
  const merged = [...local];
  for (const r of remote) {
    if (!seen.has(r.ticker)) {
      merged.push(r);
      seen.add(r.ticker);
    }
  }
  return merged.slice(0, 8);
}

// ── AUTOCOMPLETE UI ──────────────────────────────────────────

function renderSuggestions(box, results) {
  box.style.display = "block";
  box.innerHTML = results
    .map(
      (r, i) => `
    <div class="suggestion-item${i === selectedSuggestion ? " active" : ""}"
         onmousedown="selectSuggestion('${r.ticker}', '${r.name.replace(/'/g, "\\'")}', '${r.sector}')"
         onmouseenter="selectedSuggestion=${i}; highlightSuggestion()">
      <span class="suggestion-ticker">${r.ticker}</span>
      <span class="suggestion-name">${r.name}</span>
      ${r.exchange ? `<span class="suggestion-exchange">${r.exchange}</span>` : ""}
    </div>`,
    )
    .join("");
}

function showSuggestions(val) {
  const box = document.getElementById("suggestions");
  selectedSuggestion = -1;
  clearTimeout(searchTimeout);

  if (!val || val.length < 2) {
    box.style.display = "none";
    return;
  }

  const instant = searchLocal(val);
  if (instant.length > 0) {
    renderSuggestions(box, instant);
  } else {
    box.innerHTML = `<div class="suggestion-loading">Buscando...</div>`;
    box.style.display = "block";
  }

  searchTimeout = setTimeout(async () => {
    const results = await searchEmpresas(val);
    if (!results.length) {
      box.innerHTML = `<div class="suggestion-loading">Sin resultados para "${val}"</div>`;
      return;
    }
    renderSuggestions(box, results);
  }, 300);
}

function highlightSuggestion() {
  const items = document.querySelectorAll("#suggestions .suggestion-item");
  items.forEach((item, i) => {
    item.classList.toggle("active", i === selectedSuggestion);
  });
}

function handleKey(e) {
  const box = document.getElementById("suggestions");
  const items = box.querySelectorAll(".suggestion-item");
  if (e.key === "ArrowDown") {
    e.preventDefault();
    selectedSuggestion = Math.min(selectedSuggestion + 1, items.length - 1);
    highlightSuggestion();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    selectedSuggestion = Math.max(selectedSuggestion - 1, 0);
    highlightSuggestion();
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (selectedSuggestion >= 0 && items[selectedSuggestion]) {
      items[selectedSuggestion].dispatchEvent(new Event("mousedown"));
    }
  } else if (e.key === "Escape") {
    box.style.display = "none";
  }
}

document.addEventListener("click", (e) => {
  if (
    !e.target.closest("#comps-empresa") &&
    !e.target.closest("#suggestions")
  ) {
    const box = document.getElementById("suggestions");
    if (box) box.style.display = "none";
  }
});

// ── SELECCIÓN DE EMPRESA ──────────────────────────────────────

async function selectSuggestion(ticker, name, sector) {
  selectedTicker = ticker;
  document.getElementById("comps-empresa").value = `${name} (${ticker})`;
  document.getElementById("suggestions").style.display = "none";
  // habilitar inputs una vez seleccionada empresa
  document.getElementById("comps-revenue").disabled = false;
  document.getElementById("comps-sector").disabled = false;
  document.getElementById("comps-region").disabled = false;
  document.getElementById("btn-comps").disabled = false;

  if (sector) {
    autoMapSector(sector);
  } else {
    await autoDetectSector(ticker);
  }
  await fetchRevenueCard(ticker, name);
}

function autoMapSector(yfSector) {
  const sectorMap = {
    Technology: "Technology",
    "Financial Services": "Financials",
    Healthcare: "Health Insurance",
    Energy: "Energy",
    "Consumer Cyclical": "Consumer",
    "Consumer Defensive": "Consumer",
    "Real Estate": "Real Estate",
    Industrials: "Industrials",
    "Basic Materials": "Industrials",
    "Communication Services": "Technology",
    Utilities: "Industrials",
  };
  const mapped = sectorMap[yfSector] || yfSector;
  const sel = document.getElementById("comps-sector");
  const hint = document.getElementById("detect-hint");
  let found = false;
  for (let opt of sel.options) {
    if (opt.value === mapped) {
      sel.value = mapped;
      found = true;
      break;
    }
  }
  if (!found) sel.add(new Option(mapped, mapped, true, true));
  if (hint) {
    hint.textContent = `✓ Sector: ${mapped}`;
    hint.style.color = "var(--gold)";
  }
}

async function autoDetectSector(ticker) {
  try {
    const res = await fetch(`${API}/financials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    });
    if (!res.ok) return;
    const data = await res.json();
    if (data?.sector) autoMapSector(data.sector);
  } catch (err) {
    console.error("autoDetectSector error:", err);
  }
}
function getPaisSafe(e) {
  return e?.País || e?.Pais || null;
}

function renderCharts(data) {
  const empresas = data.empresas_filtradas || data.empresas || [];

  document.getElementById("comps-charts").style.display = "block";

  Chart.getChart("chart-ev-rev")?.destroy();
  Chart.getChart("chart-multiples")?.destroy();

  const scatter = empresas.map((e) => ({
    x: e["Revenue ($mm)"],
    y: e["EV ($mm)"],
    label: e.Ticker,
  }));

  const ctx1 = document.getElementById("chart-ev-rev");
  new Chart(ctx1, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Comps",
          data: scatter,
          backgroundColor: scatter.map((e) =>
            e.label === selectedTicker ? "#b8860b" : "#86BC25",
          ),
          pointRadius: scatter.map((e) => (e.label === selectedTicker ? 6 : 3)),
        },
      ],
    },
    options: {
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const r = ctx.raw;

              const fmt = (v) => {
                if (!v) return "-";
                if (v >= 1000) return `$${(v / 1000).toFixed(1)}B`;
                return `$${v.toFixed(0)}M`;
              };

              return [`${r.label}`, `Revenue: ${fmt(r.x)}`, `EV: ${fmt(r.y)}`];
            },
          },
        },
      },

      scales: {
        x: { type: "logarithmic" },
        y: { type: "logarithmic" },
      },
    },
  });

  const ctx2 = document.getElementById("chart-multiples");

  new Chart(ctx2, {
    type: "bar",
    data: {
      labels: empresas.map((e) => e.Ticker),
      datasets: [
        {
          label: "EV/EBITDA",
          data: empresas.map((e) => e["EV/EBITDA"]),
          backgroundColor: empresas.map((e) =>
            e.Ticker === selectedTicker ? "#b8860b" : "#86BC25",
          ),
          borderColor: "#86BC25",
          borderWidth: 1,
        },
      ],
    },
    options: {
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.raw.toFixed(1)}x`,
          },
        },
      },
    },
  });
}
// ── REVENUE CARD ──────────────────────────────────────────────
async function fetchRevenueCard(ticker, name) {
  const container = document.getElementById("revenue-preview");

  container.innerHTML = `
    <div class="rev-loading">
      Cargando datos financieros…
    </div>
  `;

  container.style.display = "block";

  try {
    const res = await fetch(`${API}/financials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();

    console.log("RAW /financials response:");
    console.dir(data);

    const f = data?.financials || {};

    const revenue = f?.revenue_mm ? f.revenue_mm * 1e6 : null;
    const ebitda = f?.ebitda_mm ? f.ebitda_mm * 1e6 : null;
    const ev = f?.ev_mm ? f.ev_mm * 1e6 : null;
    const marketCap = f?.mkt_cap_mm ? f.mkt_cap_mm * 1e6 : null;
    const price = f?.price ?? null;

    const fmtVal = (v) => {
      if (!v) return "—";

      const mm = v / 1e6;

      if (Math.abs(mm) >= 1000) {
        return `$${(mm / 1000).toFixed(1)}B`;
      }

      return `$${mm.toFixed(0)}M`;
    };

    if (revenue != null) {
      const revenueInput = document.getElementById("comps-revenue");
      if (revenueInput) {
        revenueInput.value = Math.round(revenue / 1e6).toLocaleString("en-US");
      }
    }

    container.innerHTML = `
      <div class="rev-card">

        <div class="rev-card-header">
          <div class="rev-company">
            <span class="rev-ticker-badge">${ticker}</span>
            <span class="rev-name-text">${name}</span>
          </div>
        </div>

        <div class="rev-grid rev-grid-5">

          <div class="rev-metric rev-metric--main">
            <div class="rev-metric-label">Revenue</div>
            <div class="rev-metric-value">${fmtVal(revenue)}</div>
          </div>

          <div class="rev-metric">
            <div class="rev-metric-label">EBITDA</div>
            <div class="rev-metric-value">${fmtVal(ebitda)}</div>
          </div>

          <div class="rev-metric">
            <div class="rev-metric-label">Enterprise Value</div>
            <div class="rev-metric-value">${fmtVal(ev)}</div>
          </div>

          <div class="rev-metric">
            <div class="rev-metric-label">Market Cap</div>
            <div class="rev-metric-value">${fmtVal(marketCap)}</div>
          </div>

          <div class="rev-metric">
            <div class="rev-metric-label">Price</div>
            <div class="rev-metric-value">
              ${price != null ? `$${price}` : "—"}
            </div>
          </div>

        </div>

        <div class="rev-source">
          Fuente: Yahoo Finance · TTM Financials
        </div>

      </div>
    `;
  } catch (err) {
    console.error("fetchRevenueCard ERROR:", err);

    container.innerHTML = `
      <div class="rev-error">
        No se pudieron cargar datos para <strong>${ticker}</strong>.
      </div>
    `;
  }
}
function toggleColumn(col) {
  COLUMN_STATE[col] = !COLUMN_STATE[col];

  document.querySelectorAll(`[data-col="${col}"]`).forEach((el) => {
    el.style.display = COLUMN_STATE[col] ? "" : "none";
  });
}
// ── GENERAR COMPS ─────────────────────────────────────────────

async function runComps() {
  const rawEmpresa = document.getElementById("comps-empresa").value || "Target";
  const empresa =
    selectedTicker || rawEmpresa.match(/\((.*?)\)/)?.[1] || rawEmpresa;
  const revenue =
    parseFloat(
      document.getElementById("comps-revenue").value.replace(/,/g, ""),
    ) || 1000;
  const sector = document.getElementById("comps-sector").value;
  const region = document.getElementById("comps-region")?.value || "GLOBAL";
  const analista =
    document.getElementById("comps-analista")?.value || "Analista";
  const escala = document.getElementById("comps-escala")?.value || "mm";
  const moneda = document.getElementById("comps-moneda")?.value || "USD";
  const rangoMin =
    parseFloat(document.getElementById("comps-rango-min")?.value) || 30;
  const rangoMax =
    parseFloat(document.getElementById("comps-rango-max")?.value) || 300;

  const btn = document.getElementById("btn-comps");
  document.getElementById("result-comps").innerHTML = spinner(
    "DESCARGANDO TTM FINANCIALS...",
  );
  btn.disabled = true;

  try {
    const body = {
      mensaje: `Comps de ${empresa} en ${sector}`,
      analista,
      empresa_override: empresa,
      sector_override: sector,
      revenue_override: revenue,
      escala,
      moneda,
      rango_min_pct: rangoMin,
      rango_max_pct: rangoMax,
      region,
    };
    console.log("BODY /comps →", body);
    const res = await fetch(`${API}/comps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    let data = null;
    let text = "";

    try {
      text = await res.text();
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      console.error("Respuesta no JSON en /comps:", text);
    }

    if (data?.empresas_filtradas) {
      data.empresas_filtradas.forEach((e) => {
        console.log("PAIS:", e.Ticker, getPaisSafe(e));
        console.log("REGION:", getRegionFromCountry(e.Pais));
      });

      const arg = data.empresas_filtradas.filter((e) => e.Pais === "Argentina");
      console.log("ARGENTINA COUNT:", arg.length);
    }

    if (!res.ok) {
      console.error("ERROR /comps status:", res.status);
      console.error("ERROR /comps body:", data || text);
      throw new Error(data?.detail || `HTTP ${res.status}`);
    }

    renderCompsResult(data);
  } catch (e) {
    document.getElementById("result-comps").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}
function getRegionFromCountry(pais) {
  if (!pais) return "OTHER";

  if (
    [
      "Argentina",
      "Brazil",
      "Mexico",
      "Chile",
      "Colombia",
      "Peru",
      "Uruguay",
      "Paraguay",
      "Bolivia",
      "Ecuador",
      "Venezuela",
    ].includes(pais)
  ) {
    return "LATAM";
  }

  if (["United States", "USA", "United States of America"].includes(pais)) {
    return "US";
  }

  if (
    [
      "Germany",
      "France",
      "Spain",
      "Italy",
      "Luxembourg",
      "Ireland",
      "Netherlands",
      "Switzerland",
      "Sweden",
      "Norway",
      "Denmark",
      "Finland",
      "Belgium",
      "Austria",
      "United Kingdom",
      "UK",
    ].includes(pais)
  ) {
    return "EU";
  }

  if (
    [
      "China",
      "Hong Kong",
      "Singapore",
      "India",
      "Japan",
      "Indonesia",
      "South Korea",
      "Taiwan",
      "Thailand",
      "Philippines",
      "Malaysia",
      "Vietnam",
      "Pakistan",
      "Bangladesh",
      "Saudi Arabia",
      "UAE",
      "Qatar",
      "Israel",
    ].includes(pais)
  ) {
    return "ASIA";
  }

  if (["South Africa", "Egypt", "Nigeria", "Kenya", "Morocco"].includes(pais)) {
    return "AFRICA";
  }

  if (["Australia", "New Zealand"].includes(pais)) {
    return "OCEANIA";
  }

  return "OTHER";
}

let COLUMN_STATE = {};

// ── RENDER COMPS RESULT ───────────────────────────────────────
function renderCompsTable(empresas) {
  const selectedRegion =
    document.getElementById("comps-region")?.value || "GLOBAL";

  return empresas
    .sort((a, b) => {
      const ra = getRegionFromCountry(getPaisSafe(a));
      const rb = getRegionFromCountry(getPaisSafe(b));

      if (ra === selectedRegion && rb !== selectedRegion) return -1;
      if (ra !== selectedRegion && rb === selectedRegion) return 1;

      return (b["Revenue ($mm)"] || 0) - (a["Revenue ($mm)"] || 0);
    })
    .map(
      (e) => `
      <tr>
        <td class="t-ticker">${e.Ticker}</td>
        <td class="t-name">${e.Empresa || ""}</td>
        <td class="t-region">${getRegionFromCountry(getPaisSafe(e))}</td>

        <td class="t-num">${fmtNum(e["Revenue ($mm)"])}</td>
        <td class="t-num">${fmtNum(e["EBITDA ($mm)"])}</td>
        <td class="t-num">${fmtNum(e["EV ($mm)"])}</td>

        <td class="t-mult">${fmtMult(e["EV/Revenue"])}</td>
        <td class="t-mult">${fmtMult(e["EV/EBITDA"])}</td>

        <td class="t-mult" data-col="pe">${fmtMult(e["P/E"])}</td>
        <td class="t-num" data-col="mktcap">${fmtNum(e["Mkt Cap ($mm)"])}</td>
        <td class="t-pct" data-col="growth">${fmtPct(e["Rev Growth %"])}</td>

        <td class="t-pct">${fmtPct(e["EBITDA Mg%"])}</td>
        <td class="t-ttm">${e.ttm_method === "quarterly" ? "✓ Q4" : "⚠ FY"}</td>
      </tr>`,
    )
    .join("");
}

function toggleCompsView(view) {
  if (!CURRENT_COMPS_DATA) return;

  CURRENT_VIEW = view;

  const empresas =
    view === "universe"
      ? CURRENT_COMPS_DATA.empresas_universe
      : CURRENT_COMPS_DATA.empresas_filtradas;

  // actualizar tabla
  document.querySelector(".comps-table tbody").innerHTML =
    renderCompsTable(empresas);
  Object.keys(COLUMN_STATE).forEach((col) => {
    if (!COLUMN_STATE[col]) {
      document.querySelectorAll(`[data-col="${col}"]`).forEach((el) => {
        el.style.display = "none";
      });
    }
  });
  // actualizar gráficos
  renderCharts({
    empresas_filtradas: empresas,
  });
}

function renderCompsResult(data) {
  CURRENT_COMPS_DATA = data;
  CURRENT_VIEW = "filtradas";
  const filtradas = data.empresas_filtradas || [];
  const stats = data.stats_filtradas?.metrics || {};
  const quality = data.ttm_quality || {};

  const ttmPct = quality.pct_real_ttm ?? 0;
  const ttmBadge =
    ttmPct >= 80
      ? `<span class="ttm-badge ttm-good">TTM ${ttmPct}%</span>`
      : ttmPct >= 50
        ? `<span class="ttm-badge ttm-warn">TTM ${ttmPct}%</span>`
        : `<span class="ttm-badge ttm-bad">TTM ${ttmPct}%</span>`;

  const selectedRegion =
    document.getElementById("comps-region")?.value || "GLOBAL";

  const tableRows = filtradas
    .sort((a, b) => {
      const ra = getRegionFromCountry(getPaisSafe(a));
      const rb = getRegionFromCountry(getPaisSafe(b));

      if (ra === selectedRegion && rb !== selectedRegion) return -1;
      if (ra !== selectedRegion && rb === selectedRegion) return 1;

      return (b["Revenue ($mm)"] || 0) - (a["Revenue ($mm)"] || 0);
    })
    .map(
      (e) => `
    <tr>
      <td class="t-ticker">${e.Ticker}</td>
      <td class="t-name">${e.Empresa || ""}</td>
      <td class="t-region">${getRegionFromCountry(getPaisSafe(e))}</td>

      <td class="t-num">${fmtNum(e["Revenue ($mm)"])}</td>
      <td class="t-num">${fmtNum(e["EBITDA ($mm)"])}</td>
      <td class="t-num">${fmtNum(e["EV ($mm)"])}</td>

      <td class="t-mult">${fmtMult(e["EV/Revenue"])}</td>
      <td class="t-mult">${fmtMult(e["EV/EBITDA"])}</td>

      <td class="t-mult" data-col="pe">${fmtMult(e["P/E"])}</td>
      <td class="t-num" data-col="mktcap">${fmtNum(e["Mkt Cap ($mm)"])}</td>
      <td class="t-pct" data-col="growth">${fmtPct(e["Rev Growth %"])}</td>

      <td class="t-pct">${fmtPct(e["EBITDA Mg%"])}</td>
      <td class="t-ttm">${e.ttm_method === "quarterly" ? "✓ Q4" : "⚠ FY"}</td>
    </tr>`,
    )
    .join("");
  document.getElementById("result-comps").innerHTML = `
    <div class="result-box">

      <div class="result-header">
        <div class="result-title">
          Comps — ${data.empresa_target} · ${data.sector} TTM
        </div>
        <div class="result-date">${new Date().toLocaleDateString("es-AR")}</div>
      </div>

      <div class="result-body">

        <!-- CHECKBOXES -->
       <div class="comps-controls" style="margin-bottom:12px;">
          <label><input type="checkbox" data-col="pe"> P/E</label>
          <label style="margin-left:12px;"><input type="checkbox" data-col="mktcap"> Mkt Cap</label>
          <label style="margin-left:12px;"><input type="checkbox" data-col="growth"> Growth</label>
        </div>

        <div class="kpi-row">
          <div class="kpi" onclick="toggleCompsView('universe')" style="cursor:pointer;">
            <div class="kpi-label">Total de la industria</div>
            <div class="kpi-value">${data.n_empresas_universe}</div>
          </div>

          <div class="kpi" onclick="toggleCompsView('filtradas')" style="cursor:pointer;">
            <div class="kpi-label">Empresas que cumplen con el filtro de revenue</div>
            <div class="kpi-value">${data.n_empresas_filtradas}</div>
          </div>
        </div>

        <div class="comps-table-wrapper">
          <table class="comps-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th>Region</th>
                <th>Revenue</th>
                <th>EBITDA</th>
                <th>EV</th>
                <th>EV/Rev</th>
                <th>EV/EBITDA</th>

                <th data-col="pe">P/E</th>
                <th data-col="mktcap">Mkt Cap</th>
                <th data-col="growth">Growth</th>

                <th>EBITDA Mg</th>
                <th>TTM</th>
              </tr>
            </thead>
            <tbody>
              ${tableRows}
            </tbody>
          </table>
        </div>

        <!-- DEAL INTELLIGENCE -->
      <button class="btn-secondary" id="btn-deal-intel" 
        onclick="triggerDealIntel()"
        style="background:#111;color:#f5f0e8;margin-right:10px;">
        🧠 DEAL INTELLIGENCE
      </button>

        <!-- BOTON EXCEL (LO RECUPERAMOS) -->
        <button class="btn-secondary" onclick="downloadCompsExcel()">
          ⬇ DESCARGAR EXCEL
        </button>

      </div>
    </div>
  `;

  // listeners
  document.querySelectorAll("input[data-col]").forEach((cb) => {
    cb.addEventListener("change", (e) => {
      toggleColumn(e.target.dataset.col, e.target.checked);
    });
  });

  // ocultar por default
  toggleColumn("pe", false);
  toggleColumn("mktcap", false);
  toggleColumn("growth", false);

  renderCharts(data);
  // Store for deal intel
  window._lastCompsData = data;
}

// ── FORMAT HELPERS ────────────────────────────────────────────

function fmtNum(val) {
  if (val == null || val === "" || isNaN(val)) return "—";
  return Number(val).toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  });
}

function fmtMult(val) {
  if (val == null || val === "" || isNaN(val)) return "—";
  return Number(val).toFixed(1) + "x";
}

function fmtPct(val) {
  if (val == null || val === "" || isNaN(val)) return "—";
  return Number(val).toFixed(1) + "%";
}

// ── EXCEL DOWNLOAD ────────────────────────────────────────────
async function downloadCompsExcel() {
  const btn = document.querySelector(".btn-secondary");
  const original = btn.innerHTML;

  btn.innerHTML = "⏳ Generando Excel...";
  btn.disabled = true;

  const empresa =
    selectedTicker ||
    document.getElementById("comps-empresa").value ||
    "Target";
  const region = document.getElementById("comps-region")?.value || "GLOBAL";
  const revenue =
    parseFloat(
      document.getElementById("comps-revenue").value.replace(/,/g, ""),
    ) || 1000;
  const sector = document.getElementById("comps-sector").value;

  try {
    const res = await fetch(`${API}/comps/excel`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        mensaje: `Comps de ${empresa} en ${sector}`,
        analista: "Analista",
        empresa_override: empresa,
        sector_override: sector,
        revenue_override: revenue,
        escala: "mm",
        moneda: "USD",
        rango_min_pct: 30,
        rango_max_pct: 300,
        region,
      }),
    });

    if (!res.ok) {
      throw new Error(`Backend ${res.status}`);
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    // Intentar abrir directo (funciona si el browser tiene Excel asociado)
    // Si no, hace download normal como fallback
    const fname = `Comps_${empresa}_${new Date().toISOString().slice(0, 10)}.xlsx`;

    // Método 1: abrir en nueva pestaña (el browser decide si abrir o descargar)
    const newWindow = window.open(url, "_blank");

    // Si el browser bloqueó el popup, fallback a descarga directa
    if (!newWindow) {
      const a = document.createElement("a");
      a.href = url;
      a.download = fname;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }

    // Limpiar URL después de un rato
    setTimeout(() => window.URL.revokeObjectURL(url), 30000);
  } catch (err) {
    alert("Error generando Excel");
    console.error(err);
  }

  btn.innerHTML = original;
  btn.disabled = false;
}
function triggerDealIntel() {
  const d = window._lastCompsData;

  if (!d) {
    console.error("No hay comps data");
    showToast("Generá comps primero", "error");
    return;
  }

  let comps = d.empresas_filtradas || d.empresas || [];

  comps = comps.slice(0, 15).map((c) => ({
    ticker: c.Ticker,
    ev: c["EV ($mm)"],
    revenue: c["Revenue ($mm)"],
    ebitda: c["EBITDA ($mm)"],
    evRev: c["EV/Rev"],
    evEbitda: c["EV/EBITDA"],
    margin: c["EBITDA Mg"],
  }));

  console.log("🧠 DEAL INTEL TRIGGER", comps);

  // 👉 LOADING STATE (CLAVE)
  const btn = document.getElementById("btn-deal-intel");
  const original = btn.innerHTML;
  btn.innerHTML = "⏳ Generando...";
  btn.disabled = true;

  fetchDealIntel(
    d.empresa_target || selectedTicker || "",
    selectedTicker || d.empresa_target || "",
    d.target_industry || "",
    d.revenue_target || 0,
    comps,
  )
    .then((data) => {
      console.log("📥 RESPONSE RAW:", data);

      if (!data || !data.briefs || data.briefs.length === 0) {
        showToast("Sin resultados de Deal Intelligence", "error");
        return;
      }

      // 👉 limpiar + fallback ticker (ESTO TE ARREGLA EL BUG ACTUAL)
      const clean = data.briefs.map((b, i) => ({
        ...b,
        ticker: b.ticker || comps[i]?.ticker || "N/A",
      }));

      renderDealIntelTable(clean);

      showToast("Deal Intelligence listo", "success");
    })
    .catch((err) => {
      console.error("Deal Intel:", err);
      showToast("Error generando Deal Intelligence", "error");
    })
    .finally(() => {
      btn.innerHTML = original;
      btn.disabled = false;
    });
}
function renderDealIntelTable(briefs) {
  const container = document.getElementById("result-comps");

  const rows = briefs
    .map(
      (b) => `
      <tr>
        <td class="t-ticker">${b.ticker}</td>
        <td class="t-mult">${b.tier || "—"}</td>
        <td class="t-name">${b.deal_thesis || "—"}</td>
        <td class="t-name">${b.risks || "—"}</td>
      </tr>
    `,
    )
    .join("");

  const html = `
    <div class="result-box" style="margin-top:20px;">

      <div class="result-header">
        <div class="result-title">
          🧠 Deal Intelligence
        </div>
      </div>

      <div class="result-body">
        <div class="comps-table-wrapper">
          <table class="comps-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Tier</th>
                <th>Deal Thesis</th>
                <th>Risks</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  `;

  container.insertAdjacentHTML("beforeend", html);
}
function showToast(msg, type = "error") {
  const el = document.createElement("div");

  el.innerText = msg;
  el.style.position = "fixed";
  el.style.bottom = "20px";
  el.style.right = "20px";
  el.style.padding = "12px 16px";
  el.style.background = type === "error" ? "#c0392b" : "#27ae60";
  el.style.color = "#fff";
  el.style.borderRadius = "6px";
  el.style.zIndex = 9999;
  el.style.fontSize = "13px";

  document.body.appendChild(el);

  setTimeout(() => el.remove(), 3000);
}
