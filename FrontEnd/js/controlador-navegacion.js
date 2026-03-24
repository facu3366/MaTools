// reloj superior
function updateTime() {
  document.getElementById("current-time").textContent =
    new Date().toLocaleTimeString("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
    });
}

updateTime();
setInterval(updateTime, 60000);

// navegación entre herramientas
async function showView(view, title) {
  document.getElementById("topbar-title").textContent = title || view;

  document
    .querySelectorAll(".nav-item:not(.disabled)")
    .forEach((n) => n.classList.remove("active"));

  event?.currentTarget?.classList?.add("active");

  const res = await fetch(`components/${view}.html`);
  const html = await res.text();

  const container = document.getElementById("app-content");
  container.innerHTML = html;

  // ESTO ES LO QUE FALTABA
  const loadedView = container.querySelector(".tool-view");
  if (loadedView) {
    loadedView.classList.add("active");
  }
}
