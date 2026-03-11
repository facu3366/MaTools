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

// generar comps
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

      headers: {
        "Content-Type": "application/json",
      },

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

          <p style="font-size:13px;color:var(--muted)">
            ${d.mensaje}
          </p>

        </div>

      </div>
    `;
  } catch (e) {
    document.getElementById("result-comps").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}
