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
        revenueInput.value = Math.round(revenue / 1e6);
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

        <div class="rev-grid">

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

// ── GENERAR COMPS ─────────────────────────────────────────────

async function runComps() {
  const rawEmpresa = document.getElementById("comps-empresa").value || "Target";
  const empresa =
    selectedTicker || rawEmpresa.match(/\((.*?)\)/)?.[1] || rawEmpresa;
  const revenue =
    parseFloat(document.getElementById("comps-revenue").value) || 1000;
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
    data.empresas_filtradas.forEach((e) => {
      console.log(e.Ticker, e.Pais);
    });

    let data = null;
    let text = "";

    try {
      text = await res.text();
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      console.error("Respuesta no JSON en /comps:", text);
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

// ── RENDER COMPS RESULT ───────────────────────────────────────

function renderCompsResult(data) {
  const filtradas = data.empresas_filtradas || [];
  const stats = data.stats_filtradas?.metrics || {};
  const quality = data.ttm_quality || {};

  const ttmPct = quality.pct_real_ttm ?? 0;
  const ttmBadge =
    ttmPct >= 80
      ? `<span class="ttm-badge ttm-good">TTM ${ttmPct}% real</span>`
      : ttmPct >= 50
        ? `<span class="ttm-badge ttm-warn">TTM ${ttmPct}% real</span>`
        : `<span class="ttm-badge ttm-bad">TTM ${ttmPct}% — revisar</span>`;

  const statCard = (label, key, suffix = "") => {
    const s = stats[key];
    if (!s || s.median == null) return "";
    return `
      <div class="fin-card">
        <div class="fin-card-label">${label}</div>
        <div class="fin-card-value">${s.median}${suffix}</div>
        <div class="fin-card-sub">Median (n=${s.count}) · Mean: ${s.mean}${suffix}</div>
      </div>`;
  };

  const tableRows = filtradas
    .sort((a, b) => (b["Revenue ($mm)"] || 0) - (a["Revenue ($mm)"] || 0))
    .map(
      (e) => `
    <tr>
      <td class="t-ticker">${e.Ticker}</td>
      <td class="t-name">${e.Empresa || ""}</td>
      <td class="t-num">${fmtNum(e["Revenue ($mm)"])}</td>
      <td class="t-num">${fmtNum(e["EBITDA ($mm)"])}</td>
      <td class="t-num">${fmtNum(e["EV ($mm)"])}</td>
      <td class="t-mult">${fmtMult(e["EV/Revenue"])}</td>
      <td class="t-mult">${fmtMult(e["EV/EBITDA"])}</td>
      <td class="t-pct">${fmtPct(e["EBITDA Mg%"])}</td>
      <td class="t-ttm">${e.ttm_method === "quarterly" ? "✓ Q4" : "⚠ FY"}</td>
    </tr>`,
    )
    .join("");

  const medianRow = `
    <tr class="stats-row stats-median">
      <td colspan="2"><strong>Median</strong></td>
      <td class="t-num">${fmtNum(stats["Revenue ($mm)"]?.median)}</td>
      <td class="t-num">${fmtNum(stats["EBITDA ($mm)"]?.median)}</td>
      <td class="t-num">${fmtNum(stats["EV ($mm)"]?.median)}</td>
      <td class="t-mult">${fmtMult(stats["EV/Revenue"]?.median)}</td>
      <td class="t-mult">${fmtMult(stats["EV/EBITDA"]?.median)}</td>
      <td class="t-pct">${fmtPct(stats["EBITDA Mg%"]?.median)}</td>
      <td></td>
    </tr>`;

  const meanRow = `
    <tr class="stats-row stats-mean">
      <td colspan="2"><strong>Mean</strong></td>
      <td class="t-num">${fmtNum(stats["Revenue ($mm)"]?.mean)}</td>
      <td class="t-num">${fmtNum(stats["EBITDA ($mm)"]?.mean)}</td>
      <td class="t-num">${fmtNum(stats["EV ($mm)"]?.mean)}</td>
      <td class="t-mult">${fmtMult(stats["EV/Revenue"]?.mean)}</td>
      <td class="t-mult">${fmtMult(stats["EV/EBITDA"]?.mean)}</td>
      <td class="t-pct">${fmtPct(stats["EBITDA Mg%"]?.mean)}</td>
      <td></td>
    </tr>`;

  document.getElementById("result-comps").innerHTML = `
    <div class="result-box">
      <div class="result-header">
        <div class="result-title">
          Comps — ${data.empresa_target} · ${data.sector} ${ttmBadge}
        </div>
        <div class="result-date">${new Date().toLocaleDateString("es-AR")}</div>
      </div>
      <div class="result-body">
        <div class="fin-grid">
          <div class="fin-card">
            <div class="fin-card-label">Universe</div>
            <div class="fin-card-value">${data.n_empresas_universe}</div>
          </div>
          <div class="fin-card">
            <div class="fin-card-label">Filtradas</div>
            <div class="fin-card-value">${data.n_empresas_filtradas}</div>
            <div class="fin-card-sub">Revenue ${fmtNum(data.rango_revenue?.min_mm)}–${fmtNum(data.rango_revenue?.max_mm)} $mm</div>
          </div>
          ${statCard("EV / Revenue", "EV/Revenue", "x")}
          ${statCard("EV / EBITDA", "EV/EBITDA", "x")}
          ${statCard("EBITDA Margin", "EBITDA Mg%", "%")}
        </div>
        <div class="comps-table-wrapper">
          <table class="comps-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Company</th>
                <th>Revenue (TTM)</th>
                <th>EBITDA (TTM)</th>
                <th>EV</th>
                <th>EV/Rev</th>
                <th>EV/EBITDA</th>
                <th>EBITDA Mg</th>
                <th>TTM</th>
              </tr>
            </thead>
            <tbody>
              ${tableRows}
              ${medianRow}
              ${meanRow}
            </tbody>
          </table>
        </div>
        <div class="comps-note">
          Revenue y EBITDA = Trailing Twelve Months (suma últimos 4 quarters reportados).
          Empresas marcadas "⚠ FY" usan dato de último año fiscal como fallback.
          Fuente: Yahoo Finance · ${new Date().toLocaleDateString("es-AR")}
        </div>
        <button class="btn-secondary" onclick="downloadCompsExcel()">
          ⬇ DESCARGAR EXCEL
        </button>
      </div>
    </div>
  `;
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
    parseFloat(document.getElementById("comps-revenue").value) || 1000;

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
