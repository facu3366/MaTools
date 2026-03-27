const API = window.API || window.location.origin;
window.API = API; // helpers visuales
function fmt(v, d = 1) {
  return v == null
    ? "—"
    : typeof v === "number"
      ? v.toLocaleString("es-AR", { maximumFractionDigits: d })
      : v;
}

function spinner(txt = "CONSULTANDO...") {
  return `
    <div class="result-box">
      <div class="spinner-wrap">
        <div class="spinner"></div>
        <div class="spinner-text">${txt}</div>
      </div>
    </div>
  `;
}

function getBancoType(n) {
  n = n || "";

  if (/NACION|PROVINCIA|CIUDAD|PROV /.test(n)) return "PÚBLICO";

  if (/DIGITAL|NARANJA|UALA/.test(n)) return "DIGITAL";

  return "PRIVADO";
}
