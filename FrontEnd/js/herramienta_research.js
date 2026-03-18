// ─────────────────────────────────────────────────────────────
//  HERRAMIENTA EQUITY RESEARCH — DealDesk
//  4 fases: Fundamentals → Earnings → DCF → Investment Thesis
//  Usa Claude API via backend para análisis profundo
// ─────────────────────────────────────────────────────────────

const RESEARCH_API =
  window.location.hostname === "localhost"
    ? "http://127.0.0.1:8000"
    : "https://web-production-f0fe2.up.railway.app";

let researchSelectedTicker = null;
let researchSearchTimeout = null;
let researchSelectedSugg = -1;

// ─────────────────────────────────────────────
// AUTOCOMPLETE — mismo patrón que Comps y DCF
// ─────────────────────────────────────────────

async function researchSearchEmpresas(query) {
  if (!query || query.length < 2) return [];
  try {
    const res = await fetch(
      `${RESEARCH_API}/yf/search?q=${encodeURIComponent(query)}`,
    );
    const data = await res.json();
    return (data.quotes || [])
      .filter((q) => ["EQUITY", "ETF"].includes(q.quoteType))
      .map((q) => ({
        ticker: q.symbol,
        name: q.longname || q.shortname || q.symbol,
        exchange: q.exchDisp || q.exchange || "",
      }));
  } catch (err) {
    console.error("Research autocomplete error:", err);
    return [];
  }
}

function researchShowSuggestions(val) {
  const box = document.getElementById("research-suggestions");
  researchSelectedSugg = -1;
  clearTimeout(researchSearchTimeout);

  if (!val || val.length < 2) {
    box.style.display = "none";
    return;
  }

  box.innerHTML = `<div class="suggestion-loading">Buscando...</div>`;
  box.style.display = "block";

  researchSearchTimeout = setTimeout(async () => {
    const results = await researchSearchEmpresas(val);
    if (!results.length) {
      box.innerHTML = `<div class="suggestion-loading">Sin resultados</div>`;
      return;
    }
    box.innerHTML = results
      .map(
        (r, i) => `
      <div class="suggestion-item" onclick="researchSelectEmpresa('${r.ticker}','${r.name.replace(/'/g, "\\'")}')">
        <span class="sugg-ticker">${r.ticker}</span>
        <span class="sugg-name">${r.name}</span>
        <span class="sugg-exchange">${r.exchange}</span>
      </div>
    `,
      )
      .join("");
  }, 350);
}

function researchSelectEmpresa(ticker, name) {
  researchSelectedTicker = ticker;
  document.getElementById("research-empresa").value = `${name} (${ticker})`;
  document.getElementById("research-suggestions").style.display = "none";
}

function researchHandleKey(e) {
  const box = document.getElementById("research-suggestions");
  const items = box.querySelectorAll(".suggestion-item");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    researchSelectedSugg = Math.min(researchSelectedSugg + 1, items.length - 1);
    items.forEach((it, i) =>
      it.classList.toggle("active", i === researchSelectedSugg),
    );
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    researchSelectedSugg = Math.max(researchSelectedSugg - 1, 0);
    items.forEach((it, i) =>
      it.classList.toggle("active", i === researchSelectedSugg),
    );
  } else if (e.key === "Enter" && researchSelectedSugg >= 0) {
    e.preventDefault();
    items[researchSelectedSugg].click();
  }
}

// ─────────────────────────────────────────────
// PHASE DEFINITIONS
// ─────────────────────────────────────────────

const PHASES = [
  {
    id: "fundamentals",
    num: "01",
    title: "Análisis de Fundamentos",
    subtitle: "10-K Deep Dive",
    icon: "◈",
    loading:
      "Analizando revenue drivers, estructura de costos y riesgos operativos...",
  },
  {
    id: "earnings",
    num: "02",
    title: "Análisis de Tendencias",
    subtitle: "Earnings History",
    icon: "◇",
    loading: "Evaluando últimos trimestres para detectar momentum o alertas...",
  },
  {
    id: "dcf",
    num: "03",
    title: "Proyección Financiera",
    subtitle: "DCF Framework",
    icon: "▣",
    loading: "Estructurando modelo DCF con supuestos de crecimiento y WACC...",
  },
  {
    id: "thesis",
    num: "04",
    title: "Tesis de Inversión",
    subtitle: "Equity Research Note",
    icon: "◉",
    loading: "Sintetizando análisis en recomendación profesional...",
  },
];

// ─────────────────────────────────────────────
// RENDER SKELETON
// ─────────────────────────────────────────────

function renderResearchSkeleton(ticker) {
  return `
    <div class="research-report">
      <div class="research-report-header">
        <div>
          <div class="research-report-eyebrow">EQUITY RESEARCH · DEEP ANALYSIS</div>
          <div class="research-report-title">${ticker}</div>
          <div class="research-report-date">${new Date().toLocaleDateString("es-AR", { day: "2-digit", month: "long", year: "numeric" })}</div>
        </div>
        <div class="research-report-badge">EN PROGRESO</div>
      </div>

      <div class="research-phases">
        ${PHASES.map(
          (p) => `
          <div class="research-phase" id="phase-${p.id}">
            <div class="phase-header">
              <div class="phase-num">${p.num}</div>
              <div class="phase-meta">
                <div class="phase-title">${p.title}</div>
                <div class="phase-subtitle">${p.subtitle}</div>
              </div>
              <div class="phase-status" id="status-${p.id}">
                <span class="phase-dot pending"></span>
                PENDIENTE
              </div>
            </div>
            <div class="phase-body" id="body-${p.id}">
              <!-- content injected here -->
            </div>
          </div>
        `,
        ).join("")}
      </div>
    </div>
  `;
}

// ─────────────────────────────────────────────
// UPDATE PHASE STATUS
// ─────────────────────────────────────────────

function setPhaseLoading(phaseId) {
  const status = document.getElementById(`status-${phaseId}`);
  const body = document.getElementById(`body-${phaseId}`);
  const phase = PHASES.find((p) => p.id === phaseId);

  status.innerHTML = `<span class="phase-dot loading"></span>ANALIZANDO`;
  status.className = "phase-status active";

  body.innerHTML = `
    <div class="phase-loading">
      <div class="phase-spinner"></div>
      <div class="phase-loading-text">${phase.loading}</div>
    </div>
  `;
  body.style.display = "block";
}

function setPhaseComplete(phaseId, htmlContent) {
  const status = document.getElementById(`status-${phaseId}`);
  const body = document.getElementById(`body-${phaseId}`);

  status.innerHTML = `<span class="phase-dot done"></span>COMPLETADO`;
  status.className = "phase-status done";

  body.innerHTML = `<div class="phase-content">${htmlContent}</div>`;
  body.style.display = "block";
}

function setPhaseError(phaseId, errorMsg) {
  const status = document.getElementById(`status-${phaseId}`);
  const body = document.getElementById(`body-${phaseId}`);

  status.innerHTML = `<span class="phase-dot error"></span>ERROR`;
  status.className = "phase-status error";

  body.innerHTML = `<div class="phase-error">${errorMsg}</div>`;
  body.style.display = "block";
}

// ─────────────────────────────────────────────
// FORMAT AI RESPONSE → HTML
// ─────────────────────────────────────────────

function formatResearchContent(text) {
  if (!text) return "<p>Sin datos disponibles.</p>";

  // Convert markdown-style headers
  let html = text
    .replace(/### (.+)/g, '<h4 class="rc-h4">$1</h4>')
    .replace(/## (.+)/g, '<h3 class="rc-h3">$1</h3>')
    .replace(/# (.+)/g, '<h2 class="rc-h2">$1</h2>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Bullet points
    .replace(/^[-•]\s+(.+)$/gm, "<li>$1</li>")
    // Line breaks
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>");

  // Wrap <li> sequences in <ul>
  html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, '<ul class="rc-list">$1</ul>');

  // Wrap in paragraph if not already
  if (!html.startsWith("<")) html = `<p>${html}</p>`;

  return html;
}

// ─────────────────────────────────────────────
// MAIN: RUN RESEARCH
// ─────────────────────────────────────────────

async function runResearch() {
  const ticker =
    researchSelectedTicker ||
    document
      .getElementById("research-empresa")
      .value.split("(")
      .pop()
      ?.replace(")", "")
      .trim()
      .toUpperCase();

  if (!ticker) {
    alert("Ingresá o seleccioná una empresa");
    return;
  }

  const btn = document.getElementById("btn-research");
  const container = document.getElementById("result-research");
  btn.disabled = true;

  // Render skeleton
  container.innerHTML = renderResearchSkeleton(ticker);

  // Run phases sequentially
  for (let i = 0; i < PHASES.length; i++) {
    const phase = PHASES[i];
    setPhaseLoading(phase.id);

    try {
      const res = await fetch(`${RESEARCH_API}/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: ticker,
          fase: phase.id,
        }),
      });

      if (!res.ok) {
        const err = await res
          .json()
          .catch(() => ({ detail: "Error del servidor" }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const content =
        data.analysis || data.resultado || data.content || JSON.stringify(data);
      setPhaseComplete(phase.id, formatResearchContent(content));
    } catch (err) {
      setPhaseError(phase.id, `Error en ${phase.title}: ${err.message}`);
      // Continue with next phases even if one fails
    }
  }

  // Update header badge
  const badge = document.querySelector(".research-report-badge");
  if (badge) {
    badge.textContent = "COMPLETADO";
    badge.classList.add("complete");
  }

  btn.disabled = false;
}

function updateTime() {
  document.getElementById("current-time").textContent =
    new Date().toLocaleTimeString("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
    });
}
updateTime();
setInterval(updateTime, 60000);
