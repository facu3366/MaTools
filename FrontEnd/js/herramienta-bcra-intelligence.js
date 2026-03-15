// ─────────────────────────────────────────────────────────────
//  BCRA INTELLIGENCE — DealDesk
//  Usa: API (de utilidades-ui.js), Chart.js (CDN), fmt/spinner/getBancoType
// ─────────────────────────────────────────────────────────────

const BCRA_COLORS = [
  "#b8860b",
  "#2d6a4f",
  "#8b1a1a",
  "#4a6fa5",
  "#c07830",
  "#6b5b73",
  "#3a7ca5",
  "#9b7b2f",
  "#5c8a4f",
  "#7a5c3a",
  "#a06040",
  "#5b7065",
  "#8b6914",
  "#3d6b5e",
  "#a0522d",
  "#6a7b4f",
  "#7b6888",
  "#4f7942",
  "#8e7360",
  "#5a8070",
];

const BCRA_METRICS = [
  { k: "activos", l: "Activos", api: "Activos" },
  { k: "depositos", l: "Depósitos", api: "Depositos" },
  { k: "prestamos", l: "Préstamos", api: "Prestamos" },
  { k: "patrimonio", l: "Patrimonio Neto", api: "Patrimonio Neto" },
];

let BCRA_BANKS = [];
let bcraBarChart = null,
  bcraPieChart = null;

const bcraState = {
  metric: "activos",
  topN: 10,

  currency: "ARS",
  scale: "millions",

  usdRates: {
    official: 1,
    mep: 1,
    blue: 1,
  },

  selected: new Set(),
  dataSource: "loading",
  fechaScraping: "",
  nBancos: 0,
};

// ── helpers ──
function bcraFmt(n) {
  if (n == null || isNaN(n)) return "—";
  if (n >= 1e12) return (n / 1e12).toFixed(1) + "T";
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "MM";
  return Math.round(n).toString();
}
function bcraFmtB(n) {
  if (n == null || isNaN(n)) return "—";

  if (bcraState.scale === "billions") return n.toFixed(1) + "B";

  if (bcraState.scale === "millions") return n.toFixed(0) + "M";

  return n.toLocaleString("es-AR");
}
function bcraML() {
  return BCRA_METRICS.find((m) => m.k === bcraState.metric).l;
}
function bcraShort(name) {
  return (name || "")
    .replace(/^BANCO (DE LA |DE |DEL |)/i, "")
    .replace(/ S\.A\..*$/i, "")
    .replace(/ COOP.*$/i, "")
    .replace(/ CIA\..*$/i, "")
    .replace(/ LTDO\.?$/i, "")
    .trim()
    .slice(0, 24);
}
function bcraActive() {
  return BCRA_BANKS.filter((b) => bcraState.selected.has(b.id));
}

// ── fetch ──
async function bcraFetchData() {
  bcraState.dataSource = "loading";
  const el = document.getElementById("bcra-kpis");
  if (el)
    el.innerHTML = `
  <div style="width:100%;text-align:center;padding:32px;color:var(--muted)">
    <div class="spinner"></div>
    <p style="margin-top:12px;font-family:'DM Mono',monospace;font-size:11px">
      SCRAPEANDO BCRA...
    </p>
    <p style="font-size:11px;margin-top:4px">
      Puede tardar 10-15 seg
    </p>
  </div>
`;
  try {
    const res = await fetch(`${API}/bcra/bancos`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    console.log(data.bancos[0]);
    if (data.error) throw new Error(data.error);
    BCRA_BANKS = data.bancos.map((b, i) => ({
      id: i,
      name: b.Banco || "N/A",
      short: bcraShort(b.Banco),
      color: BCRA_COLORS[i % BCRA_COLORS.length],
      activos: b["Activos"] || 0,
      depositos: b["Depositos"] || 0,
      prestamos: b["Prestamos"] || 0,
      patrimonio: b["Patrimonio Neto"] || 0,
    }));
    bcraState.dataSource = "api";
    bcraState.fechaScraping = data.fecha_scraping || "";
    bcraState.nBancos = data.n_bancos || BCRA_BANKS.length;
  } catch (err) {
    console.error("BCRA API error:", err.message);
    // fallback simulado mínimo
    const names = [
      "NACION ARGENTIN",
      "GALICIA Y BS AS",
      "SANTANDER",
      "BBVA ARGE",
      "MACRO SA",
      "PR BUENOS AIRES",
      "INDUSTRIAL AND",
      "PATAGONIA SA",
      "SUPERVIELLE SA",
      "CIUDAD DE BS AS",
    ];
    BCRA_BANKS = names.map((n, i) => ({
      id: i,
      name: n,
      short: n,
      color: BCRA_COLORS[i],
      activos: (10 - i) * 7e9,
      depositos: (10 - i) * 4.5e9,
      prestamos: (10 - i) * 3e9,
      patrimonio: (10 - i) * 1.5e9,
    }));
    bcraState.dataSource = "simulated";
    bcraState.fechaScraping = "Simulado";
    bcraState.nBancos = BCRA_BANKS.length;
  }
  bcraState.selected = new Set(BCRA_BANKS.map((b) => b.id));
}

// ── renders ──
function bcraRenderBadge() {
  const b = document.getElementById("bcra-badge-count");
  const m = document.getElementById("bcra-hdr-mes");
  const fx = document.getElementById("bcra-fx");

  if (b) {
    b.textContent = bcraState.selected.size + " / " + bcraState.nBancos;
    b.className =
      "nav-badge " + (bcraState.dataSource === "api" ? "live" : "soon");
  }

  if (m) {
    m.textContent =
      bcraState.fechaScraping +
      " · " +
      (bcraState.dataSource === "api" ? "LIVE" : "SIMULADO");
  }

  if (fx) {
    fx.textContent =
      "USD OF: " +
      Math.round(bcraState.usdRates.official) +
      " · BLUE: " +
      Math.round(bcraState.usdRates.blue);
  }
}

function bcraInitBankSelector() {
  const trigger = document.getElementById("bcra-bsel-trigger"),
    dd = document.getElementById("bcra-bsel-dd"),
    arrow = document.getElementById("bcra-bsel-arrow"),
    search = document.getElementById("bcra-bsel-search"),
    list = document.getElementById("bcra-bsel-list"),
    cnt = document.getElementById("bcra-bsel-cnt"),
    label = document.getElementById("bcra-bsel-label");
  if (!trigger) return;
  function ul() {
    const s = bcraState.selected;
    label.textContent =
      s.size === BCRA_BANKS.length
        ? "Todas las entidades (" + BCRA_BANKS.length + ")"
        : s.size === 0
          ? "Seleccionar bancos..."
          : s.size +
            " banco" +
            (s.size > 1 ? "s" : "") +
            " seleccionado" +
            (s.size > 1 ? "s" : "");
  }
  function rl(q) {
    q = q || "";
    const s = bcraState.selected,
      f = BCRA_BANKS.filter(
        (b) =>
          b.name.toLowerCase().includes(q.toLowerCase()) ||
          b.short.toLowerCase().includes(q.toLowerCase()),
      );
    cnt.textContent = f.length + " resultados";
    list.innerHTML = f
      .map((b) => {
        const on = s.has(b.id);
        return `<div class="bcra-bsel-item${on ? " on" : ""}" data-id="${b.id}"><div class="bcra-bsel-chk" style="${on ? "border-color:" + b.color + ";background:" + b.color : ""}">${on ? "✓" : ""}</div><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${b.name}</span></div>`;
      })
      .join("");
    list.querySelectorAll(".bcra-bsel-item").forEach((el) => {
      el.onclick = () => {
        const id = +el.dataset.id;
        if (s.has(id)) {
          if (s.size > 1) s.delete(id);
        } else s.add(id);
        rl(search.value);
        ul();
        bcraRenderAll();
      };
    });
  }
  let open = false;
  trigger.onclick = () => {
    open = !open;
    dd.classList.toggle("open", open);
    arrow.style.transform = open ? "rotate(180deg)" : "";
    if (open) {
      search.value = "";
      rl();
      search.focus();
    }
  };
  search.oninput = () => rl(search.value);
  document.getElementById("bcra-btn-all").onclick = () => {
    BCRA_BANKS.forEach((b) => bcraState.selected.add(b.id));
    rl(search.value);
    ul();
    bcraRenderAll();
  };
  document.getElementById("bcra-btn-clr").onclick = () => {
    bcraState.selected.clear();
    bcraState.selected.add(0);
    rl(search.value);
    ul();
    bcraRenderAll();
  };
  document.addEventListener("mousedown", (e) => {
    if (!document.getElementById("bcra-bsel").contains(e.target)) {
      dd.classList.remove("open");
      arrow.style.transform = "";
    }
  });
  ul();
}

function bcraInitTopN() {
  document.querySelectorAll("#bcra-topn-group button").forEach((btn) => {
    const n = +btn.dataset.n;
    btn.classList.toggle("on", n === bcraState.topN);
    btn.onclick = () => {
      bcraState.topN = n;
      bcraRenderAll();
      bcraInitTopN();
    };
  });
}

function bcraRenderKPIs() {
  const a = bcraActive();
  const el = document.getElementById("bcra-kpis");

  if (!el) return;

  el.innerHTML = BCRA_METRICS.map((m) => {
    const t = a.reduce((s, b) => s + bcraConvert(b[m.k] || 0), 0);

    return `
      <div class="bcra-kpi ${bcraState.metric === m.k ? "active" : ""}" data-k="${m.k}">
        <div class="bcra-kpi-label">${m.l}</div>
        <div class="bcra-kpi-value">${bcraFmtB(t)}</div>
      </div>
    `;
  }).join("");

  el.querySelectorAll(".bcra-kpi").forEach((k) => {
    k.onclick = () => {
      bcraState.metric = k.dataset.k;
      bcraRenderAll();
    };
  });
}

function bcraRenderBar() {
  const a = bcraActive(),
    mk = bcraState.metric,
    sorted = [...a]
      .sort((a, b) => (b[mk] || 0) - (a[mk] || 0))
      .slice(0, bcraState.topN);
  document.getElementById("bcra-rank-title").textContent =
    `Top ${bcraState.topN} por ${bcraML()}`;
  const canvas = document.getElementById("bcra-chart-bar"),
    wrap = canvas.parentElement;
  wrap.style.height = Math.max(200, bcraState.topN * 26 + 30) + "px";
  if (bcraBarChart) bcraBarChart.destroy();
  bcraBarChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: sorted.map((b) => b.short),
      datasets: [
        {
          data: sorted.map((b) => bcraConvert(b[mk] || 0)),
          backgroundColor: sorted.map((b) => b.color),
          borderRadius: 3,
          barThickness: 18,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      onClick: (e, els) => {
        if (els.length) {
          bcraState.selected = new Set([sorted[els[0].index].id]);
          bcraRenderAll();
          bcraInitBankSelector();
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#fff",
          borderColor: "#d4cfc4",
          borderWidth: 1,
          titleColor: "#7a7060",
          bodyColor: "#0e0e0e",
          callbacks: { label: (ctx) => bcraFmtN(ctx.raw) + " miles de pesos" },
        },
      },
      scales: {
        x: {
          grid: { color: "#ede7d9" },
          ticks: { callback: (v) => bcraFmt(v) },
        },
        y: {
          grid: { display: false },
          ticks: { font: { weight: 600, size: 11 }, color: "#0e0e0e" },
        },
      },
    },
  });
}

function bcraRenderPie() {
  const a = bcraActive(),
    mk = bcraState.metric,
    sorted = [...a].sort((x, y) => (y[mk] || 0) - (x[mk] || 0)),
    total = sorted.reduce((s, b) => s + (b[mk] || 0), 0),
    top5 = sorted.slice(0, 5),
    rest = sorted.slice(5);
  const items = top5.map((b) => ({
    name: b.short,
    value: b[mk] || 0,
    color: b.color,
    pct: total > 0 ? ((b[mk] / total) * 100).toFixed(1) : "0.0",
  }));
  if (rest.length) {
    const rv = rest.reduce((s, b) => s + (b[mk] || 0), 0);
    items.push({
      name: "Otros (" + rest.length + ")",
      value: rv,
      color: "#b0a890",
      pct: total > 0 ? ((rv / total) * 100).toFixed(1) : "0.0",
    });
  }
  document.getElementById("bcra-pie-title").textContent =
    "Composición — " + bcraML();
  document.getElementById("bcra-pie-legend").innerHTML = items
    .map(
      (d) =>
        `<div class="bcra-pie-item"><div class="sq" style="background:${d.color}"></div><span class="nm">${d.name}</span><span class="pc">${d.pct}%</span></div>`,
    )
    .join("");
  if (bcraPieChart) bcraPieChart.destroy();
  bcraPieChart = new Chart(document.getElementById("bcra-chart-pie"), {
    type: "doughnut",
    data: {
      labels: items.map((d) => d.name),
      datasets: [
        {
          data: items.map((d) => d.value),
          backgroundColor: items.map((d) => d.color),
          borderWidth: 2,
          borderColor: "#fff",
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "60%",
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#fff",
          borderColor: "#d4cfc4",
          borderWidth: 1,
          titleColor: "#7a7060",
          bodyColor: "#0e0e0e",
          callbacks: {
            label: (ctx) =>
              bcraFmtN(ctx.raw) + " (" + items[ctx.dataIndex].pct + "%)",
          },
        },
      },
    },
  });
}

function bcraRenderLine() {
  const wrap = document.getElementById("bcra-ts-wrap"),
    title = document.getElementById("bcra-ts-title");
  if (title) title.textContent = "Evolución histórica — " + bcraML();
  if (wrap)
    wrap.innerHTML = `<div style="text-align:center;padding:40px 20px;color:var(--muted)"><p style="font-family:'DM Mono',monospace;font-size:11px;letter-spacing:1px">DATOS HISTÓRICOS NO DISPONIBLES</p><p style="font-size:12px;margin-top:8px">Para ver evolución temporal se necesita persistir datos mensuales (PostgreSQL).</p></div>`;
}

function bcraRenderRatios() {
  const a = bcraActive(),
    mk = bcraState.metric,
    sorted = [...a]
      .sort((x, y) => (y[mk] || 0) - (x[mk] || 0))
      .slice(0, bcraState.topN);
  document.getElementById("bcra-ratios-list").innerHTML = sorted
    .map((b) => {
      const ld =
          b.depositos > 0
            ? ((b.prestamos / b.depositos) * 100).toFixed(1)
            : "—",
        lev = b.patrimonio > 0 ? (b.activos / b.patrimonio).toFixed(1) : "—";
      return `<div class="bcra-ratio"><div class="dot" style="background:${b.color}"></div><span class="nm">${b.short}</span><div class="vals" style="text-align:right"><div class="ld">L/D ${ld}%</div><div class="lv">Lev ${lev}x</div></div></div>`;
    })
    .join("");
}

function bcraRenderTable() {
  const a = bcraActive(),
    mk = bcraState.metric,
    sorted = [...a]
      .sort((x, y) => (y[mk] || 0) - (x[mk] || 0))
      .slice(0, bcraState.topN);
  document.getElementById("bcra-tbl-sub").textContent =
    (bcraState.fechaScraping || "—") + " · Top " + bcraState.topN;
  document.getElementById("bcra-tbl-body").innerHTML = sorted
    .map(
      (b, i) =>
        `<tr data-id="${b.id}">
  <td style="color:var(--muted);font-weight:600">${i + 1}</td>
  <td style="font-weight:500;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
    <span class="dot" style="background:${b.color}"></span>${b.short}
  </td>
  <td class="r">${bcraFmtN(bcraConvert(b.activos))}</td>
  <td class="r">${bcraFmtN(bcraConvert(b.depositos))}</td>
  <td class="r">${bcraFmtN(bcraConvert(b.prestamos))}</td>
  <td class="r">${bcraFmtN(bcraConvert(b.patrimonio))}</td>
</tr>`,
    )
    .join("");
  document.querySelectorAll("#bcra-tbl-body tr").forEach((tr) => {
    tr.onclick = () => {
      bcraState.selected = new Set([+tr.dataset.id]);
      bcraRenderAll();
      bcraInitBankSelector();
    };
  });
}

function bcraRenderAll() {
  bcraRenderBadge();
  bcraRenderKPIs();
  bcraRenderBar();
  bcraRenderPie();
  bcraRenderLine();
  bcraRenderRatios();
  bcraRenderTable();
  bcraInitTopN();
}

async function initBCRADashboard() {
  Chart.defaults.color = "#7a7060";
  Chart.defaults.borderColor = "#d4cfc4";
  Chart.defaults.font.family = "'DM Sans',sans-serif";
  Chart.defaults.font.size = 11;

  await bcraFetchFX();
  await bcraFetchData();

  bcraInitBankSelector();
  bcraInitTopN();
  bcraRenderAll();

  // eventos de moneda
  document.getElementById("bcra-currency").onchange = (e) => {
    bcraState.currency = e.target.value;
    bcraRenderAll();
  };

  // eventos de escala
  document.getElementById("bcra-scale").onchange = (e) => {
    bcraState.scale = e.target.value;
    bcraRenderAll();
  };
}
async function bcraFetchFX() {
  try {
    const res = await fetch("https://api.bluelytics.com.ar/v2/latest");
    const data = await res.json();

    console.log("FX API response:", data);

    bcraState.usdRates.official = data.oficial?.value_avg || 1;
    bcraState.usdRates.blue = data.blue?.value_avg || 1;

    // si no hay MEP usamos blue como fallback
    bcraState.usdRates.mep = data.mep?.value_avg || data.blue?.value_avg || 1;

    console.log("FX rates guardados:", bcraState.usdRates);
  } catch (e) {
    console.warn("FX API error", e);
  }
}
function bcraConvert(v) {
  if (!v) return 0;

  let value = v;

  if (bcraState.currency === "USD_OFF")
    value = value / bcraState.usdRates.official;

  if (bcraState.currency === "USD_MEP") value = value / bcraState.usdRates.mep;

  if (bcraState.currency === "USD_BLUE")
    value = value / bcraState.usdRates.blue;

  if (bcraState.scale === "millions") value = value / 1e6;

  if (bcraState.scale === "billions") value = value / 1e9;

  return value;
}

function bcraFmtN(n) {
  if (n == null || isNaN(n)) return "—";

  return n.toLocaleString("es-AR", {
    maximumFractionDigits: 1,
  });
}
