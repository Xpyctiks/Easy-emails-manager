// Shared by every page: theme switch, toasts (flash messages + htmx HX-Trigger "showToast"), confirmation dialog
// (data-confirm on buttons and hx-confirm on htmx elements), tooltips, request progress bar, password eye buttons.

// Tabler bundles Bootstrap and exposes it as window.tabler.bootstrap
window.bootstrap = window.bootstrap || (window.tabler && window.tabler.bootstrap);

// ---------------------------------------------------------------- theme
function setTheme(theme) {
  document.documentElement.setAttribute("data-bs-theme", theme);
  try { localStorage.setItem("eem_theme", theme); } catch (e) {}
}

// ---------------------------------------------------------------- toasts
const TOAST_ICONS = { success: "✓", danger: "✕", warning: "!", info: "i" };

function showToast(message, level) {
  level = (level || "info").replace("alert alert-", "");
  if (!["success", "danger", "warning", "info"].includes(level)) level = "info";
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const el = document.createElement("div");
  el.className = `toast align-items-center border-0 app-toast app-toast-${level}`;
  el.setAttribute("role", level === "danger" ? "alert" : "status");
  el.innerHTML = `<div class="d-flex"><div class="toast-body d-flex gap-2"><span class="app-toast-icon"></span><span class="app-toast-text"></span></div>
    <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Закрити"></button></div>`;
  el.querySelector(".app-toast-icon").textContent = TOAST_ICONS[level];
  el.querySelector(".app-toast-text").textContent = message;   // textContent: messages may contain email data
  container.appendChild(el);
  const toast = new bootstrap.Toast(el, { delay: level === "danger" ? 10000 : 5000 });
  el.addEventListener("hidden.bs.toast", () => el.remove());
  toast.show();
}

// ---------------------------------------------------------------- confirmation dialog
function confirmDialog(text) {
  return new Promise(resolve => {
    const el = document.getElementById("confirmModal");
    if (!el) { resolve(window.confirm(text)); return; }
    el.querySelector("#confirmText").textContent = text;
    const modal = bootstrap.Modal.getOrCreateInstance(el);
    let answered = false;
    const ok = el.querySelector("#confirmOk");
    const onOk = () => { answered = true; modal.hide(); resolve(true); };
    ok.addEventListener("click", onOk, { once: true });
    el.addEventListener("hidden.bs.modal", () => {
      ok.removeEventListener("click", onOk);
      if (!answered) resolve(false);
    }, { once: true });
    modal.show();
    setTimeout(() => ok.focus(), 200);
  });
}

// plain form buttons with data-confirm="question"
document.addEventListener("click", e => {
  const btn = e.target.closest("[data-confirm]");
  if (!btn || btn.dataset.confirmed === "1") return;
  e.preventDefault();
  e.stopImmediatePropagation();
  confirmDialog(btn.dataset.confirm).then(ok => {
    if (!ok) return;
    btn.dataset.confirmed = "1";
    const form = btn.form || btn.closest("form");
    if (form && btn.type === "submit") form.requestSubmit(btn);
    else btn.click();
    delete btn.dataset.confirmed;
  });
}, true);

// htmx elements with hx-confirm="question" - same dialog instead of window.confirm
document.addEventListener("htmx:confirm", e => {
  if (!e.detail.question) return;
  e.preventDefault();
  confirmDialog(e.detail.question).then(ok => { if (ok) e.detail.issueRequest(true); });
});

// ---------------------------------------------------------------- tooltips
function initTooltips(root) {
  (root || document).querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    bootstrap.Tooltip.getOrCreateInstance(el, { trigger: "hover" });
  });
}

function hideTooltips() {
  document.querySelectorAll(".tooltip").forEach(t => t.remove());
}

// ---------------------------------------------------------------- htmx integration
document.addEventListener("showToast", e => showToast(e.detail.message, e.detail.level));
document.addEventListener("htmx:beforeRequest", () => document.body.classList.add("is-loading"));
document.addEventListener("htmx:afterRequest", () => document.body.classList.remove("is-loading"));
document.addEventListener("htmx:beforeSwap", hideTooltips);
document.addEventListener("htmx:afterSettle", e => initTooltips(e.detail.elt));
document.addEventListener("htmx:responseError", e => {
  showToast(`Помилка сервера (${e.detail.xhr.status}). Дивіться лог.`, "danger");
});
document.addEventListener("htmx:sendError", () => showToast("Немає зв'язку з сервером.", "danger"));

// ---------------------------------------------------------------- page load
document.addEventListener("DOMContentLoaded", () => {
  const themeBtn = document.getElementById("themeToggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      setTheme(document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark");
    });
  }

  try {
    const flashes = JSON.parse(document.getElementById("flashData")?.textContent || "[]");
    flashes.forEach(([category, message]) => showToast(message, category));
  } catch (e) {}

  initTooltips();

  document.addEventListener("click", e => {
    const eye = e.target.closest("[data-toggle-password]");
    if (!eye) return;
    e.preventDefault();
    const input = document.getElementById(eye.dataset.togglePassword);
    if (input) input.type = input.type === "password" ? "text" : "password";
  });

  document.querySelectorAll("form.needs-validation").forEach(form => {
    form.addEventListener("submit", e => {
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
      }
      form.classList.add("was-validated");
    });
  });

  // regular (non-htmx) form posts: show the progress bar until the next page arrives
  document.addEventListener("submit", e => {
    if (!e.defaultPrevented && !e.target.hasAttribute("hx-get") && !e.target.hasAttribute("hx-post")) {
      document.body.classList.add("is-loading");
    }
  });
});

window.addEventListener("pageshow", e => { if (e.persisted) document.body.classList.remove("is-loading"); });
