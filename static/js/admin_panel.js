// Admin panel: default port hint by the chosen encryption type.

document.addEventListener("DOMContentLoaded", () => {
  const security = document.getElementById("newSecurity");
  const port = document.getElementById("newPort");
  if (security && port) {
    const update = () => { port.placeholder = security.value === "ssl" ? "993" : "143"; };
    security.addEventListener("change", update);
    update();
  }
});
