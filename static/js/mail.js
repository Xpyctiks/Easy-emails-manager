// Three-pane mail page: domain filter/sort, active items, keyboard navigation, bulk selection,
// sort direction button and pane switching on narrow (mobile) screens.

const DOMAIN_SORT_KEY = "eem_domain_sort";
const app = () => document.getElementById("mailApp");

function setView(view) {
  const el = app();
  if (el) el.dataset.view = view;
}

// ---------------------------------------------------------------- left pane: domains
function applyDomainFilter() {
  const text = (document.getElementById("domainFilter")?.value || "").trim().toLowerCase();
  let visible = 0;
  document.querySelectorAll("#domainList .domain-item").forEach(item => {
    const match = !text || item.dataset.name.includes(text);
    item.classList.toggle("d-none", !match);
    if (match) visible++;
  });
  document.getElementById("noDomainMatches")?.classList.toggle("d-none", visible !== 0 || !text);
}

function applyDomainSort() {
  const select = document.getElementById("domainSort");
  const list = document.getElementById("domainList");
  if (!select || !list) return;
  const [field, dir] = select.value.split("-");
  const sign = dir === "asc" ? 1 : -1;
  const items = Array.from(list.querySelectorAll(".domain-item"));
  items.sort((a, b) => {
    let res;
    if (field === "name") res = a.dataset.name.localeCompare(b.dataset.name);
    else if (field === "count") res = Number(a.dataset.count) - Number(b.dataset.count);
    else res = a.dataset.last.localeCompare(b.dataset.last);
    return res * sign || a.dataset.name.localeCompare(b.dataset.name);
  });
  const marker = document.getElementById("noDomainMatches");
  items.forEach(item => list.insertBefore(item, marker));
  try { localStorage.setItem(DOMAIN_SORT_KEY, select.value); } catch (e) {}
}

function markActive(selector, el) {
  document.querySelectorAll(selector + ".active").forEach(x => x.classList.remove("active"));
  if (el) el.classList.add("active");
}

// ---------------------------------------------------------------- middle pane: selection
function updateBulkBar() {
  const bar = document.getElementById("bulkBar");
  if (!bar) return;
  const all = document.querySelectorAll("#emailList .row-check");
  const checked = document.querySelectorAll("#emailList .row-check:checked");
  bar.classList.toggle("d-none", checked.length === 0);
  document.getElementById("selectedCount").textContent = checked.length;
  const checkAll = document.getElementById("checkAll");
  if (checkAll) {
    checkAll.checked = all.length > 0 && checked.length === all.length;
    checkAll.indeterminate = checked.length > 0 && checked.length < all.length;
  }
  document.querySelectorAll("#emailList .email-row").forEach(row => {
    row.classList.toggle("selected", !!row.querySelector(".row-check:checked"));
  });
}

let lastChecked = null;

// ---------------------------------------------------------------- keyboard: ↑/↓ or J/K through the emails
function moveSelection(step) {
  const rows = Array.from(document.querySelectorAll("#emailList .email-row"));
  if (!rows.length) return;
  const current = rows.findIndex(r => r.classList.contains("active"));
  const next = rows[Math.max(0, Math.min(rows.length - 1, current + step))] || rows[0];
  if (next && next !== rows[current]) {
    next.scrollIntoView({ block: "nearest" });
    next.click();
  }
}

document.addEventListener("keydown", e => {
  // Ctrl+Enter in the reply form sends it
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.closest(".reply-form")) {
    e.preventDefault();
    e.target.closest(".reply-form").requestSubmit();
    return;
  }
  if (e.target.closest("input, textarea, select, [contenteditable]") || e.ctrlKey || e.metaKey || e.altKey) {
    if (e.key === "Escape" && e.target.id === "domainFilter") { e.target.value = ""; applyDomainFilter(); }
    return;
  }
  if (document.querySelector(".modal.show")) return;
  // while a reply is being written, don't let the arrow keys replace it with another email
  if (document.querySelector("#readPane .reply-form")) return;
  if (e.key === "r" || e.key === "к") { const btn = document.getElementById("replyBtn"); if (btn) { e.preventDefault(); btn.click(); } return; }
  if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); moveSelection(1); }
  else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); moveSelection(-1); }
  else if (e.key === "Enter" && e.target.classList.contains("email-row")) { e.target.click(); }
  else if (e.key === "/") { e.preventDefault(); document.querySelector('#listControls input[name="q"]')?.focus(); }
});

// ---------------------------------------------------------------- events
document.addEventListener("click", e => {
  const back = e.target.closest("[data-view-go]");
  if (back) { setView(back.dataset.viewGo); return; }

  const domain = e.target.closest(".domain-item");
  if (domain) { markActive(".domain-item", domain); return; }

  const row = e.target.closest(".email-row");
  if (row) { markActive(".email-row", row); return; }

  if (e.target.closest("#sortOrderBtn")) {
    const order = document.getElementById("sortOrder");
    order.value = order.value === "asc" ? "desc" : "asc";
    document.querySelector("#sortOrderBtn .order-asc").classList.toggle("d-none", order.value !== "asc");
    document.querySelector("#sortOrderBtn .order-desc").classList.toggle("d-none", order.value === "asc");
    htmx.trigger("#sortField", "change");
    return;
  }

  if (e.target.id === "bulkCancel") {
    document.querySelectorAll("#emailList .row-check:checked").forEach(c => { c.checked = false; });
    updateBulkBar();
  }
});

document.addEventListener("change", e => {
  if (e.target.id === "replyFiles") {
    const list = document.getElementById("replyFilesList");
    const files = Array.from(e.target.files || []);
    if (list && files.length) {
      const total = files.reduce((s, f) => s + f.size, 0);
      list.textContent = files.map(f => f.name).join(", ") + ` (${(total / 1048576).toFixed(1)} МБ)`;
    }
    return;
  }
  if (e.target.id === "checkAll") {
    document.querySelectorAll("#emailList .row-check").forEach(c => { c.checked = e.target.checked; });
    updateBulkBar();
  } else if (e.target.classList.contains("row-check")) {
    updateBulkBar();
  }
});

// shift+click selects a range of checkboxes
document.addEventListener("click", e => {
  const box = e.target.closest(".row-check");
  if (!box) return;
  const boxes = Array.from(document.querySelectorAll("#emailList .row-check"));
  if (e.shiftKey && lastChecked && boxes.includes(lastChecked)) {
    const [a, b] = [boxes.indexOf(lastChecked), boxes.indexOf(box)].sort((x, y) => x - y);
    boxes.slice(a, b + 1).forEach(x => { x.checked = box.checked; });
    updateBulkBar();
  }
  lastChecked = box;
});

// mobile: show the pane that just received new content
document.addEventListener("htmx:afterSwap", e => {
  const id = e.detail.target.id;
  if (id === "listPane") setView("list");
  if (id === "readPane" && e.detail.target.querySelector(".read-header")) setView("read");
  if (id === "readPane" && !e.detail.target.querySelector(".read-header")) {
    markActive(".email-row", null);
    if (app()?.dataset.view === "read") setView("list");
  }
  if (id === "emailList" || id === "listPane") updateBulkBar();
});

document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("domainSort");
  if (select) {
    try {
      const saved = localStorage.getItem(DOMAIN_SORT_KEY);
      if (saved && select.querySelector(`option[value="${saved}"]`)) select.value = saved;
    } catch (e) {}
    select.addEventListener("change", applyDomainSort);
    applyDomainSort();
  }
  document.getElementById("domainFilter")?.addEventListener("input", applyDomainFilter);
  document.querySelector(".domain-item.active")?.scrollIntoView({ block: "center" });
  document.querySelector(".email-row.active")?.scrollIntoView({ block: "center" });
});
