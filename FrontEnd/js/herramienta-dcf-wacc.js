const API = "https://web-production-f0fe2.up.railway.app";
let bcraData = null,
  bcraMetric = "Activos";

// TIME
function updateTime() {
  document.getElementById("current-time").textContent =
    new Date().toLocaleTimeString("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
    });
}
updateTime();
setInterval(updateTime, 60000);

// NAV
function showView(id, title) {
  document
    .querySelectorAll(".tool-view")
    .forEach((v) => v.classList.remove("active"));
  document
    .querySelectorAll(".nav-item:not(.disabled)")
    .forEach((n) => n.classList.remove("active"));
  document.getElementById("view-" + id).classList.add("active");
  document.getElementById("topbar-title").textContent = title || id;
  event?.currentTarget?.classList?.add("active");
}

// HELPERS
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

// AUTOCOMPLETE
const EMPRESA_LIST = [
  {
    name: "Mercado Libre",
    alias: ["meli", "mercado libre", "mercadolibre"],
    ticker: "MELI",
    sector: "Technology",
  },
  {
    name: "Apple",
    alias: ["apple", "aapl"],
    ticker: "AAPL",
    sector: "Technology",
  },
  {
    name: "Microsoft",
    alias: ["microsoft", "msft"],
    ticker: "MSFT",
    sector: "Technology",
  },
  {
    name: "Alphabet (Google)",
    alias: ["google", "alphabet", "googl"],
    ticker: "GOOGL",
    sector: "Technology",
  },
  {
    name: "Amazon",
    alias: ["amazon", "amzn"],
    ticker: "AMZN",
    sector: "Technology",
  },
  {
    name: "Meta",
    alias: ["meta", "facebook", "fb"],
    ticker: "META",
    sector: "Technology",
  },
  {
    name: "NVIDIA",
    alias: ["nvidia", "nvda"],
    ticker: "NVDA",
    sector: "Technology",
  },
  {
    name: "Salesforce",
    alias: ["salesforce", "crm"],
    ticker: "CRM",
    sector: "Technology",
  },
  {
    name: "Shopify",
    alias: ["shopify", "shop"],
    ticker: "SHOP",
    sector: "Technology",
  },
  {
    name: "Sea Limited",
    alias: ["sea", "se"],
    ticker: "SE",
    sector: "Technology",
  },
  {
    name: "JPMorgan",
    alias: ["jpmorgan", "jpm", "jp morgan"],
    ticker: "JPM",
    sector: "Financials",
  },
  {
    name: "Goldman Sachs",
    alias: ["goldman", "gs"],
    ticker: "GS",
    sector: "Financials",
  },
  {
    name: "Banco Galicia",
    alias: ["galicia", "ggal"],
    ticker: "GGAL",
    sector: "Financials",
  },
  {
    name: "UnitedHealth",
    alias: ["unitedhealth", "unh"],
    ticker: "UNH",
    sector: "Health Insurance",
  },
  {
    name: "ExxonMobil",
    alias: ["exxon", "xom"],
    ticker: "XOM",
    sector: "Energy",
  },
  { name: "YPF", alias: ["ypf"], ticker: "YPF", sector: "Energy" },
  {
    name: "Walmart",
    alias: ["walmart", "wmt"],
    ticker: "WMT",
    sector: "Consumer",
  },
  {
    name: "Prologis",
    alias: ["prologis", "pld"],
    ticker: "PLD",
    sector: "Real Estate",
  },
];

let selectedSuggestion = -1;

function showSuggestions(val) {
  const box = document.getElementById("suggestions");

  if (!val || val.length < 2) {
    box.style.display = "none";
    return;
  }

  const q = val.toLowerCase();

  const matches = EMPRESA_LIST.filter(
    (e) =>
      e.name.toLowerCase().includes(q) ||
      e.alias.some((a) => a.includes(q)) ||
      e.ticker.toLowerCase().includes(q),
  ).slice(0, 6);

  if (!matches.length) {
    box.style.display = "none";
    return;
  }

  box.innerHTML = matches
    .map(
      (e, i) => `
    <div onclick="selectSuggestion(${i})" id="sug-${i}"
      style="padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--line);font-size:13px;display:flex;justify-content:space-between;align-items:center"
      onmouseover="this.style.background='var(--cream)'" onmouseout="this.style.background='var(--white)'">
      <span>
        <strong style="font-family:'DM Mono',monospace;font-size:11px;color:var(--gold)">
          ${e.ticker}
        </strong>
        &nbsp;${e.name}
      </span>
      <span style="font-family:'DM Mono',monospace;font-size:9px;color:var(--muted)">
        ${e.sector}
      </span>
    </div>
  `,
    )
    .join("");

  box._matches = matches;
  box.style.display = "block";
  selectedSuggestion = -1;
}

async function selectSuggestion(i) {
  const box = document.getElementById("suggestions");
  const e = box._matches[i];
  const hint = document.getElementById("detect-hint");

  document.getElementById("comps-empresa").value = e.name;
  document.getElementById("comps-sector").value = e.sector;
  document.getElementById("comps-revenue").value = "";

  box.style.display = "none";

  hint.style.color = "var(--muted)";
  hint.textContent = `⏳ Consultando Yahoo Finance para ${e.ticker}...`;

  try {
    const res = await fetch(`${API}/financials`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: e.ticker,
        incluir_wacc: false,
      }),
    });

    const data = await res.json();
    const rev = data?.financials?.revenue_mm;

    if (rev) {
      document.getElementById("comps-revenue").value = Math.round(rev);

      hint.style.color = "var(--gold)";

      hint.textContent = `✓ ${e.ticker} · ${e.sector} · $${Math.round(rev).toLocaleString()}mm (Yahoo Finance)`;
    } else {
      hint.textContent = `✓ ${e.ticker} · ${e.sector} — ingresá el revenue manualmente`;
    }
  } catch (err) {
    hint.style.color = "var(--error)";

    hint.textContent = `⚠ API no disponible — ingresá el revenue manualmente`;
  }
}

function handleKey(event) {
  const box = document.getElementById("suggestions");

  if (box.style.display === "none") return;

  const items = box.querySelectorAll("div");

  if (event.key === "ArrowDown") {
    selectedSuggestion = Math.min(selectedSuggestion + 1, items.length - 1);

    items.forEach(
      (el, i) =>
        (el.style.background =
          i === selectedSuggestion ? "var(--cream)" : "var(--white)"),
    );

    event.preventDefault();
  } else if (event.key === "ArrowUp") {
    selectedSuggestion = Math.max(selectedSuggestion - 1, 0);

    items.forEach(
      (el, i) =>
        (el.style.background =
          i === selectedSuggestion ? "var(--cream)" : "var(--white)"),
    );

    event.preventDefault();
  } else if (event.key === "Enter" && selectedSuggestion >= 0) {
    selectSuggestion(selectedSuggestion);
    event.preventDefault();
  } else if (event.key === "Escape") {
    box.style.display = "none";
  }
}

document.addEventListener("click", (e) => {
  if (!e.target.closest("#suggestions") && e.target.id !== "comps-empresa")
    document.getElementById("suggestions").style.display = "none";
});

function autoDetect() {}

// COMPS
async function runComps() {
  const empresa = document.getElementById("comps-empresa").value || "Target";
  const revenue =
    parseFloat(document.getElementById("comps-revenue").value) || 1000;
  const sector = document.getElementById("comps-sector").value;
  const analista =
    document.getElementById("comps-analista").value || "Analista";

  const escala = document.getElementById("comps-escala")?.value || "mm";
  const moneda = document.getElementById("comps-moneda")?.value || "USD";
  const rangoMin =
    parseFloat(document.getElementById("comps-rango-min")?.value) || 30;
  const rangoMax =
    parseFloat(document.getElementById("comps-rango-max")?.value) || 300;

  const btn = document.getElementById("btn-comps");

  document.getElementById("result-comps").innerHTML = spinner(
    "DESCARGANDO COMPS...",
  );

  btn.disabled = true;

  try {
    const res = await fetch(`${API}/comps`, {
      method: "POST",

      headers: { "Content-Type": "application/json" },

      body: JSON.stringify({
        mensaje: `Dame comps de ${empresa}`,

        analista,

        empresa_override: empresa,

        sector_override: sector,

        revenue_override: revenue,

        moneda,

        escala,

        rango_min_pct: rangoMin,

        rango_max_pct: rangoMax,
      }),
    });

    const d = await res.json();

    if (!res.ok || d.detail) {
      document.getElementById("result-comps").innerHTML =
        `<div class="error-msg">Error API: ${d.detail || JSON.stringify(d)}</div>`;

      btn.disabled = false;
      return;
    }

    window._lastComps = {
      empresa,
      sector,
      revenue,
      escala,
      moneda,
      analista,
      rangoMin,
      rangoMax,
    };

    document.getElementById("result-comps").innerHTML = `
      <div class="result-box">
        <div class="result-header">
          <div class="result-title">
            Comps — ${d.empresa_target || empresa}
          </div>
          <div class="result-date">
            ${new Date().toLocaleDateString("es-AR")}
          </div>
        </div>

        <div class="result-body">

          <div class="fin-grid">

            <div class="fin-card">
              <div class="fin-card-label">Sector</div>
              <div class="fin-card-value" style="font-size:16px">
                ${d.sector}
              </div>
            </div>

            <div class="fin-card">
              <div class="fin-card-label">Universe</div>
              <div class="fin-card-value">${d.n_empresas_universe}</div>
              <div class="fin-card-sub">empresas totales</div>
            </div>

            <div class="fin-card">
              <div class="fin-card-label">Comparables</div>
              <div class="fin-card-value">${d.n_empresas_filtradas}</div>
              <div class="fin-card-sub">
                rango ${rangoMin}%–${rangoMax}%
              </div>
            </div>

          </div>

          <p style="font-size:13px;color:var(--muted);margin-bottom:20px">
            ${d.mensaje}
          </p>

          <button id="btn-excel" onclick="downloadExcel()"
            style="display:inline-flex;align-items:center;gap:8px;background:var(--success);color:#fff;padding:10px 22px;font-family:'DM Mono',monospace;font-size:11px;letter-spacing:2px;border:none;cursor:pointer;text-transform:uppercase;">
            ↓ DESCARGAR EXCEL
          </button>

        </div>
      </div>`;
  } catch (e) {
    document.getElementById("result-comps").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}
// DCF
async function runDCF() {
  const ticker = document.getElementById("dcf-ticker").value.toUpperCase();

  if (!ticker) {
    alert("Ingresá un ticker");
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
        risk_free_rate: parseFloat(document.getElementById("dcf-rfr").value),
        equity_risk_premium: parseFloat(
          document.getElementById("dcf-erp").value,
        ),
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
              <div class="fin-card-value">
                ${w.wacc_pct ? w.wacc_pct + "%" : "—"}
              </div>
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

// PRECEDENTS
async function runPrecedents() {
  const btn = document.getElementById("btn-prec");

  document.getElementById("result-prec").innerHTML =
    spinner("BUSCANDO DEALS...");

  btn.disabled = true;

  try {
    const evMin = document.getElementById("prec-ev-min").value;

    const body = {
      sector: document.getElementById("prec-sector").value,
      region: document.getElementById("prec-region").value,
      años: parseInt(document.getElementById("prec-years").value),
    };

    if (evMin) body.min_ev_mm = parseFloat(evMin);

    const res = await fetch(`${API}/precedents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const d = await res.json();

    const deals = d.deals || [];
    const s = d.estadisticas || {};

    document.getElementById("result-prec").innerHTML = `
      <div class="result-box">
        <div class="result-header">
          <div class="result-title">
            Precedentes — ${body.sector} · ${body.region}
          </div>
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
              <div class="fin-card-value">
                ${s.ev_mediana_mm ? "$" + fmt(s.ev_mediana_mm) + "mm" : "—"}
              </div>
            </div>

            <div class="fin-card">
              <div class="fin-card-label">EV/EBITDA Med.</div>
              <div class="fin-card-value">
                ${s.ev_ebitda_mediana ? fmt(s.ev_ebitda_mediana) + "x" : "—"}
              </div>
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
// BCRA
async function runBCRA() {
  const btn = document.getElementById("btn-bcra");

  document.getElementById("result-bcra").innerHTML =
    spinner("SCRAPEANDO BCRA...");

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
