let bcraData = null;
let bcraMetric = "Activos";

// Cargar datos del BCRA
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

// Render de la tabla BCRA
function renderBCRA(data, metric) {
  bcraMetric = metric;

  const t = data.totales;

  const bancos = [...data.bancos].sort(
    (a, b) => (b[metric] || 0) - (a[metric] || 0),
  );

  const maxVal = bancos[0]?.[metric] || 1;

  const totalVal = bancos.reduce((s, b) => s + (b[metric] || 0), 0);

  document.getElementById("result-bcra").innerHTML = `

    <div class="result-box" style="margin-top:24px">

      <div class="result-header">
        <div class="result-title">
          Sistema Financiero — ${data.fecha_scraping}
        </div>
        <div class="result-date">
          BCRA
        </div>
      </div>

      <div class="result-body">

        <div class="bcra-stats">

          <div class="bcra-stat">
            <div class="bcra-stat-label">Activos Totales</div>
            <div class="bcra-stat-value">
              ${t.activos_total_b_ars ? Math.round(t.activos_total_b_ars) : "—"}
            </div>
            <div class="bcra-stat-unit">
              Miles de millones ARS
            </div>
          </div>

          <div class="bcra-stat">
            <div class="bcra-stat-label">Depósitos</div>
            <div class="bcra-stat-value">
              ${t.depositos_total_b_ars ? Math.round(t.depositos_total_b_ars) : "—"}
            </div>
            <div class="bcra-stat-unit">
              Miles de millones ARS
            </div>
          </div>

          <div class="bcra-stat">
            <div class="bcra-stat-label">Patrimonio Neto</div>
            <div class="bcra-stat-value">
              ${t.patrimonio_total_b_ars ? Math.round(t.patrimonio_total_b_ars) : "—"}
            </div>
            <div class="bcra-stat-unit">
              Miles de millones ARS
            </div>
          </div>

          <div class="bcra-stat">
            <div class="bcra-stat-label">Entidades</div>
            <div class="bcra-stat-value">
              ${data.n_bancos}
            </div>
            <div class="bcra-stat-unit">
              del sistema
            </div>
          </div>

        </div>

        <div class="metric-tabs">

          <button class="metric-tab ${metric === "Activos" ? "active" : ""}"
            onclick="renderBCRA(bcraData,'Activos')">
            ACTIVOS
          </button>

          <button class="metric-tab ${metric === "Depositos" ? "active" : ""}"
            onclick="renderBCRA(bcraData,'Depositos')">
            DEPÓSITOS
          </button>

          <button class="metric-tab ${metric === "Patrimonio Neto" ? "active" : ""}"
            onclick="renderBCRA(bcraData,'Patrimonio Neto')">
            PATR. NETO
          </button>

          <button class="metric-tab ${metric === "Prestamos" ? "active" : ""}"
            onclick="renderBCRA(bcraData,'Prestamos')">
            PRÉSTAMOS
          </button>

        </div>

        <table class="data-table">

          <thead>
            <tr>
              <th>#</th>
              <th>ENTIDAD</th>
              <th style="text-align:right">ACTIVOS (B)</th>
              <th style="text-align:right">DEPÓSITOS (B)</th>
              <th style="text-align:right">PATR. NETO (B)</th>
              <th>% SISTEMA</th>
            </tr>
          </thead>

          <tbody>

            ${bancos
              .map((b, i) => {
                const val = b[metric] || 0;

                const pct = totalVal > 0 ? (val / totalVal) * 100 : 0;

                const barW = maxVal > 0 ? (val / maxVal) * 100 : 0;

                return `

                <tr>

                  <td>
                    <span class="rank-num ${i < 3 ? "rank-top" : ""}">
                      ${String(i + 1).padStart(2, "0")}
                    </span>
                  </td>

                  <td>
                    <div class="banco-name-cell">
                      ${b.Banco || "—"}
                    </div>

                    <div class="banco-type-cell">
                      ${getBancoType(b.Banco)}
                    </div>
                  </td>

                  <td class="num-cell">
                    ${b["Activos (B ARS)"] ? b["Activos (B ARS)"].toFixed(1) : "—"}
                  </td>

                  <td class="num-cell">
                    ${b["Depositos (B ARS)"] ? b["Depositos (B ARS)"].toFixed(1) : "—"}
                  </td>

                  <td class="num-cell">
                    ${b["Patrimonio Neto (B ARS)"] ? b["Patrimonio Neto (B ARS)"].toFixed(1) : "—"}
                  </td>

                  <td>

                    <div class="pct-row">

                      <div class="pct-bar-bg">

                        <div class="pct-bar-fill"
                          style="width:${barW}%">
                        </div>

                      </div>

                      <div class="pct-label">
                        ${pct.toFixed(1)}%
                      </div>

                    </div>

                  </td>

                </tr>

              `;
              })
              .join("")}

          </tbody>

        </table>

      </div>

    </div>

  `;
}
