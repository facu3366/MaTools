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
