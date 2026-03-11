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

      headers: {
        "Content-Type": "application/json",
      },

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

          <div class="result-date">
            ${d.periodo || ""}
          </div>

        </div>

        <div class="result-body">

          <div class="fin-grid">

            <div class="fin-card">
              <div class="fin-card-label">Deals</div>
              <div class="fin-card-value">
                ${s.n_deals || deals.length}
              </div>
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

      </div>

    `;
  } catch (e) {
    document.getElementById("result-prec").innerHTML =
      `<div class="error-msg">Error: ${e.message}</div>`;
  }

  btn.disabled = false;
}
