// ODR Mux Manager web UI. Plain ES module, no build step.
// All DOM is built with h(), which only ever creates text nodes for content,
// so user-provided strings are never parsed as HTML.

/* ============================== utilities ============================== */

const ICONS = {
  brand: [["path", "M4.9 19.1C1 15.2 1 8.8 4.9 4.9M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5M19.1 4.9C23 8.8 23 15.1 19.1 19"], ["circle", 12, 12, 2]],
  grid: [["path", "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"]],
  layers: [["path", "M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"]],
  activity: [["path", "M22 12h-4l-3 9L9 3l-3 9H2"]],
  import: [["path", "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"]],
  upload: [["path", "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"]],
  code: [["path", "M16 18l6-6-6-6M8 6l-6 6 6 6"]],
  users: [["path", "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"], ["circle", 9, 7, 4]],
  user: [["path", "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"], ["circle", 12, 7, 4]],
  sliders: [["path", "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"]],
  audit: [["path", "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8"]],
  logout: [["path", "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"]],
  search: [["circle", 11, 11, 8], ["path", "M21 21l-4.35-4.35"]],
  plus: [["path", "M12 5v14M5 12h14"]],
  x: [["path", "M18 6 6 18M6 6l12 12"]],
  check: [["path", "M20 6 9 17l-5-5"]],
  alert: [["path", "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01"]],
  link: [["path", "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"]],
  image: [["rect", 3, 3, 18, 18, 2], ["circle", 8.5, 8.5, 1.5], ["path", "M21 15l-5-5L5 21"]],
  refresh: [["path", "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"]],
  trash: [["path", "M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"]],
  folder: [["path", "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"]],
  folderPlus: [["path", "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2zM12 11v6M9 14h6"]],
  file: [["path", "M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM13 2v7h7"]],
  calendar: [["rect", 3, 4, 18, 18, 2], ["path", "M16 2v4M8 2v4M3 10h18"]],
  chevronsLeft: [["path", "M11 17l-5-5 5-5M18 17l-5-5 5-5"]],
  chevronsRight: [["path", "M13 17l5-5-5-5M6 17l5-5-5-5"]],
  arrowLeft: [["path", "M19 12H5M12 19l-7-7 7-7"]],
  arrowUp: [["path", "M12 19V5M5 12l7-7 7 7"]],
  copy: [["rect", 9, 9, 13, 13, 2], ["path", "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"]],
  edit: [["path", "M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"]],
  zap: [["path", "M13 2 3 14h9l-1 8 10-12h-9l1-8z"]],
  shield: [["path", "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"]],
  globe: [["circle", 12, 12, 10], ["path", "M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"]],
  lock: [["rect", 3, 11, 18, 11, 2], ["path", "M7 11V7a5 5 0 0 1 10 0v4"]],
  info: [["circle", 12, 12, 10], ["path", "M12 16v-4M12 8h.01"]],
  menu: [["path", "M3 12h18M3 6h18M3 18h18"]],
  clock: [["circle", 12, 12, 10], ["path", "M12 6v6l4 2"]],
  radio: [["path", "M4.9 19.1C1 15.2 1 8.8 4.9 4.9M19.1 4.9C23 8.8 23 15.1 19.1 19"], ["circle", 12, 12, 2]],
  sun: [["circle", 12, 12, 4], ["path", "M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"]],
  moon: [["path", "M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"]],
  monitor: [["rect", 2, 3, 20, 14, 2], ["path", "M8 21h8M12 17v4"]],
  heart: [["path", "M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"]],
  login: [["path", "M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"]],
  braces: [["path", "M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1"]],
  play: [["path", "M5 3l14 9-14 9V3z"]],
  arrowDown: [["path", "M12 5v14M19 12l-7 7-7-7"]],
  volume: [["path", "M11 5 6 9H2v6h4l5 4V5zM19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"]],
  server: [["rect", 2, 2, 20, 8, 2], ["rect", 2, 14, 20, 8, 2], ["path", "M6 6h.01M6 18h.01"]],
  database: [["path", "M21 5c0 1.66-4 3-9 3S3 6.66 3 5s4-3 9-3 9 1.34 9 3zM21 12c0 1.66-4 3-9 3s-9-1.34-9-3M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"]],
  tv: [["rect", 2, 7, 20, 15, 2], ["path", "M17 2l-5 5-5-5"]],
  shuffle: [["path", "M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"]],
  power: [["path", "M18.36 6.64a9 9 0 1 1-12.73 0M12 2v10"]],
  eye: [["path", "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"], ["circle", 12, 12, 3]],
  history: [["path", "M3 3v5h5M3.05 13A9 9 0 1 0 6 5.3L3 8M12 7v5l4 2"]],
  wifiOff: [["path", "M1 1l22 22M16.72 11.06A10.94 10.94 0 0 1 19 12.55M5 12.55a10.94 10.94 0 0 1 5.17-2.39M10.71 5.05A16 16 0 0 1 22.58 9M1.42 9a15.91 15.91 0 0 1 4.7-2.88M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"]],
};

const SVGNS = "http://www.w3.org/2000/svg";
function icon(name) {
  const svg = document.createElementNS(SVGNS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  for (const [kind, ...a] of ICONS[name] || []) {
    const el = document.createElementNS(SVGNS, kind);
    if (kind === "path") el.setAttribute("d", a[0]);
    if (kind === "circle") { el.setAttribute("cx", a[0]); el.setAttribute("cy", a[1]); el.setAttribute("r", a[2]); }
    if (kind === "rect") { el.setAttribute("x", a[0]); el.setAttribute("y", a[1]); el.setAttribute("width", a[2]); el.setAttribute("height", a[3]); el.setAttribute("rx", a[4]); }
    svg.appendChild(el);
  }
  return svg;
}

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "value") el.value = v;
      else if (k === "checked") el.checked = !!v;
      else if (k === "disabled") el.disabled = !!v;
      else if (k === "selected") el.selected = !!v;
      else if (k === "ref") v(el);
      else el.setAttribute(k, v === true ? "" : v);
    }
  }
  append(el, children);
  return el;
}
function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const put = (el, ...children) => append(el, children);
function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
function btn(label, opts = {}) {
  // "Save..." buttons take part in the unsaved-changes guard: editing a field near one marks it dirty,
  // clicking it clears that again
  const isSave = typeof label === "string" && /^Save\b/.test(label) && /primary/.test(opts.cls || "") && opts.onclick;
  const onclick = isSave ? (e) => { DIRTY.delete(b); return opts.onclick(e); } : opts.onclick;
  const b = h("button", { class: "btn " + (opts.cls || ""), type: opts.type || "button", onclick, disabled: opts.disabled, title: opts.title },
    opts.icon ? icon(opts.icon) : null, label);
  if (isSave) { b.dataset.save = "1"; b._save = opts.onclick; }
  return b;
}

/* ---- unsaved changes: warn before a tab/page switch throws edits away ---- */
const DIRTY = new Set();
function liveDirty() { for (const b of [...DIRTY]) if (!b.isConnected) DIRTY.delete(b); return [...DIRTY]; }
function trackDirty(container) {
  const mark = (e) => {
    const el = e.target;
    if (!(el instanceof HTMLElement) || !el.matches("input, select, textarea") || el.type === "search" || el.dataset.nodirty) return;
    // the nearest enclosing block with a Save button owns this field; stop at the page itself, so
    // filters and search boxes in the page header never count as edits
    for (let n = el.parentElement; n && n !== container; n = n.parentElement) {
      const b = n.querySelector(":scope button[data-save]");
      if (b) { DIRTY.add(b); return; }
    }
  };
  container.addEventListener("input", mark, true);
  container.addEventListener("change", mark, true);
}
window.addEventListener("beforeunload", (e) => { if (liveDirty().length) { e.preventDefault(); e.returnValue = ""; } });
function iconBtn(name, title, onclick) {
  return h("button", { class: "icon-btn", type: "button", title, "aria-label": title, onclick }, icon(name));
}

class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }

async function api(method, url, body, { form = false, quiet = false } = {}) {
  const headers = { "X-Requested-With": "odr-mux" };
  if (S.csrf) headers["X-CSRF-Token"] = S.csrf;
  const opts = { method, headers, credentials: "same-origin" };
  if (body !== undefined) {
    if (form) opts.body = body;
    else { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  }
  let r;
  try { r = await fetch(url, opts); } catch (e) {
    if (!quiet) toast("Cannot reach the server.", "error");
    throw new ApiError("network", 0);
  }
  let data = null;
  try { data = await r.json(); } catch (e) { /* empty */ }
  if (!r.ok) {
    const msg = (data && data.error) || `Request failed (${r.status})`;
    if (r.status === 401 && S.user) { S.user = null; boot(); }
    if (!quiet) toast(msg, "error");
    throw new ApiError(msg, r.status);
  }
  return data;
}

function toast(msg, kind = "") {
  const t = h("div", { class: "toast " + kind, role: kind === "error" ? "alert" : "status" }, msg);
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "error" ? 7000 : 4000);
}

function fmtAgo(ts) {
  if (!ts) return "never";
  const s = Math.round(Date.now() / 1000 - ts);
  if (s < 0) return "in " + fmtDur(-s);
  if (s < 45) return "just now";
  return fmtDur(s) + " ago";
}
function fmtDur(s) {
  if (s < 90) return `${Math.max(1, Math.round(s))}s`;
  if (s < 5400) return `${Math.round(s / 60)}m`;
  if (s < 129600) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}
function fmtIn(ts) {
  if (!ts) return "—";
  const s = Math.round(ts - Date.now() / 1000);
  return s <= 0 ? "now" : "in " + fmtDur(s);
}
function fmtDate(ts) { return ts ? new Date(ts * 1000).toLocaleString() : "—"; }
function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(2) + " MB";
}
function initials(name) {
  const w = (name || "?").trim().split(/\s+/).filter(Boolean);
  return ((w[0] || "?")[0] + (w[1] ? w[1][0] : (w[0] || "").slice(1, 2))).toUpperCase();
}
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* ============================== modal helpers ============================== */

const OPEN_MODALS = new Set();
function closeAllModals() { for (const c of [...OPEN_MODALS]) c(); }
function modal({ title, body, foot, wide = false, onclose }) {
  const back = h("div", { class: "modal-back" });
  const close = () => { OPEN_MODALS.delete(close); back.remove(); document.removeEventListener("keydown", esc); onclose && onclose(); };
  OPEN_MODALS.add(close);
  const esc = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", esc);
  const box = h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true" },
    h("div", { class: "modal-head" }, h("h2", null, title), h("span", { class: "spacer" }), iconBtn("x", "Close", close)),
    h("div", { class: "modal-body" }, body),
    foot ? h("div", { class: "modal-foot" }, foot) : null);
  back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
  back.appendChild(box);
  document.body.appendChild(back);
  const first = box.querySelector("input, select, textarea");
  if (first) setTimeout(() => first.focus(), 30);
  return { close, box };
}

function confirmDialog(text, { okText = "Confirm", danger = false, title = "Are you sure?" } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const m = modal({
      title, body: h("p", null, text),
      foot: [btn("Cancel", { onclick: () => m.close() }),
        btn(okText, { cls: danger ? "danger" : "primary", onclick: () => { done = true; m.close(); resolve(true); } })],
      onclose: () => { if (!done) resolve(false); },
    });
  });
}

function showSecret(title, text, secret) {
  const m = modal({
    title, body: h("div", { class: "stack" }, h("p", null, text), codeBlock(secret)),
    foot: btn("Done", { cls: "primary", onclick: () => m.close() }),
  });
}

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => toast("Copied to clipboard.", "ok"));
  } else {
    const ta = h("textarea", { class: "hidden-copy" });
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("Copied to clipboard.", "ok"); } catch (e) { toast("Copy failed - select the text manually.", "error"); }
    ta.remove();
  }
}

function codeBlock(text) {
  return h("div", { class: "code" }, text, h("span", { class: "copy" }, iconBtn("copy", "Copy", () => copyText(text))));
}

// Server-side file browser (admin only). mode: "dir" | "file" | "save"
function fileBrowser({ title = "Choose a location", mode = "dir", exts = "", start = "/", filename = "" } = {}) {
  return new Promise((resolve) => {
    let cur = null, selected = null, done = false;
    const pathBar = h("div", { class: "fs-path" });
    const list = h("div", { class: "fs-list" });
    const info = h("div", { class: "small muted" });
    const nameInput = mode === "save" ? h("input", { type: "text", class: "mono", value: filename || "output.dat" }) : null;
    const chooseBtn = btn(mode === "dir" ? "Use this folder" : mode === "save" ? "Save here" : "Select file", { cls: "primary", onclick: choose });

    async function load(path) {
      let data;
      try { data = await api("GET", `/api/fs?path=${encodeURIComponent(path)}${exts ? "&files=" + encodeURIComponent(exts) : ""}`); }
      catch (e) { if (cur === null && path !== "/") return load("/"); return; }
      cur = data.path; selected = null;
      clear(pathBar);
      const parts = cur.split("/").filter(Boolean);
      pathBar.appendChild(h("button", { onclick: () => load("/") }, "/"));
      parts.forEach((p, i) => {
        pathBar.appendChild(h("button", { onclick: () => load("/" + parts.slice(0, i + 1).join("/")) }, p));
        if (i < parts.length - 1) pathBar.appendChild(h("span", { class: "muted" }, "/"));
      });
      clear(list);
      if (data.parent) list.appendChild(h("div", { class: "fs-item dir", onclick: () => load(data.parent) }, icon("arrowUp"), ".."));
      if (!data.entries.length) list.appendChild(h("div", { class: "fs-item muted" }, "Empty folder"));
      for (const e of data.entries) {
        const full = (cur === "/" ? "" : cur) + "/" + e.name;
        const item = h("div", { class: "fs-item" + (e.dir ? " dir" : "") }, icon(e.dir ? "folder" : "file"),
          h("span", { class: "grow ellipsis" }, e.name), e.dir ? null : h("span", { class: "small muted" }, fmtBytes(e.size)));
        item.addEventListener("click", () => {
          if (e.dir) return load(full);
          list.querySelectorAll(".sel").forEach((x) => x.classList.remove("sel"));
          item.classList.add("sel");
          selected = full;
          if (nameInput) nameInput.value = e.name;
        });
        if (e.dir) item.addEventListener("dblclick", () => load(full));
        list.appendChild(item);
      }
      put(clear(info), data.writable
        ? h("span", { class: "chip green" }, icon("check"), "Writable by the service")
        : h("span", { class: "chip amber" }, icon("lock"), "Not writable by the service user"));
    }
    async function mkdir() {
      const name = prompt("New folder name");
      if (!name) return;
      try { const r = await api("POST", "/api/fs/mkdir", { path: cur, name }); load(r.path); } catch (e) { /* toasted */ }
    }
    function choose() {
      let result = cur;
      if (mode === "file") { if (!selected) return toast("Select a file.", "error"); result = selected; }
      if (mode === "save") {
        const n = nameInput.value.trim();
        if (!n || n.includes("/")) return toast("Enter a file name.", "error");
        result = (cur === "/" ? "" : cur) + "/" + n;
      }
      done = true; m.close(); resolve(result);
    }
    const m = modal({
      title, wide: true,
      body: h("div", { class: "stack" }, pathBar, list, h("div", { class: "row" }, info, h("span", { class: "spacer" }),
        mode !== "file" ? btn("New folder", { cls: "sm ghost", icon: "folderPlus", onclick: mkdir }) : null),
      nameInput ? h("div", { class: "field" }, h("label", null, "File name"), nameInput) : null),
      foot: [btn("Cancel", { onclick: () => m.close() }), chooseBtn],
      onclose: () => { if (!done) resolve(null); },
    });
    const startDir = mode === "save" ? (start || "/").replace(/\/[^/]*$/, "") : start;
    load(startDir || "/");
  });
}

/* ============================== form helpers ============================== */

function field(label, input, { hint, max } = {}) {
  const lbl = h("div", { class: "label-row" }, h("label", null, label));
  if (max && input.tagName !== "SELECT") {
    const count = h("span", { class: "count" });
    const upd = () => { const n = [...(input.value || "")].length; count.textContent = `${n}/${max}`; count.classList.toggle("over", n > max); };
    input.addEventListener("input", upd); upd();
    lbl.appendChild(count);
  }
  return h("div", { class: "field" }, lbl, input, hint ? h("div", { class: "hint" }, hint) : null);
}
const inp = (value, attrs = {}) => h("input", { type: "text", value: value ?? "", ...attrs });
function sel(value, options, attrs = {}) {
  return h("select", attrs, options.map(([v, l]) => h("option", { value: v, selected: String(v) === String(value) }, l)));
}
function toggle(label, checked, attrs = {}) {
  const box = h("input", { type: "checkbox", checked, ...attrs });
  return { el: h("label", { class: "check" }, box, h("span", null, label)), box };
}

/* ============================== app state ============================== */


const S = { user: null, csrf: null, version: "", muxName: "", configured: false, collapsed: false, pollTimer: null, monTimer: null, caps: null, ref: null };

/* ---------- theme (per browser) ---------- */
const THEMES = [["system", "System", "monitor"], ["light", "Light", "sun"], ["dark", "Dark", "moon"]];
function getTheme() {
  try { const t = localStorage.getItem("odrmux.theme"); return t === "light" || t === "dark" ? t : "system"; } catch (e) { return "system"; }
}
function setTheme(t) {
  try { if (t === "system") localStorage.removeItem("odrmux.theme"); else localStorage.setItem("odrmux.theme", t); } catch (e) { /* ignore */ }
  if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
}
function themeToggle() {
  const b = h("button", { class: "icon-btn", type: "button" });
  const draw = () => {
    const [, label, ic] = THEMES.find((x) => x[0] === getTheme());
    clear(b).appendChild(icon(ic));
    b.title = `Theme: ${label} (click to change)`;
    b.setAttribute("aria-label", b.title);
  };
  b.addEventListener("click", () => { const i = THEMES.findIndex((x) => x[0] === getTheme()); setTheme(THEMES[(i + 1) % THEMES.length][0]); draw(); });
  draw();
  return b;
}
function setTitle() { document.title = S.muxName ? `${S.muxName} · MPBNL Multiplex WebFrontend` : "MPBNL Multiplex WebFrontend"; }
try { S.collapsed = localStorage.getItem("odrmux.collapsed") === "1"; } catch (e) { /* ignore */ }

const ROLE_LABEL = { admin: "Administrator", editor: "Editor", viewer: "Viewer (read-only)", station: "Station monitor" };
const RANK = { station: 0, viewer: 1, editor: 2, admin: 3 };
const atLeast = (r) => S.user && RANK[S.user.role] >= RANK[r];
const isAdmin = () => atLeast("admin");
const isEditor = () => atLeast("editor");
const isViewer = () => atLeast("viewer");

const CODEC_LABEL = { mp2: "MP2", aaclc: "AAC", he: "HE", hev2: "HEv2", auto: "AAC", dabplus: "DAB+", dmb: "DMB" };
const CODEC_LONG = { mp2: "DAB (MP2)", aaclc: "DAB+ AAC-LC", he: "DAB+ HE-AAC", hev2: "DAB+ HE-AAC v2", auto: "DAB+ (encoder picks)" };
const PTY = ["None", "News", "Current Affairs", "Information", "Sport", "Education", "Drama", "Culture", "Science", "Varied",
  "Pop Music", "Rock Music", "Easy Listening", "Light Classical", "Serious Classical", "Other Music", "Weather", "Finance",
  "Children's", "Social Affairs", "Religion", "Phone In", "Travel", "Leisure", "Jazz Music", "Country Music", "National Music",
  "Oldies Music", "Folk Music", "Documentary", "(30)", "(31)"];
const LANGS = [["", "—"], ["0x09", "English"], ["0x0F", "French"], ["0x08", "German"], ["0x1D", "Dutch"], ["0x0A", "Spanish"],
  ["0x15", "Italian"], ["0x11", "Irish"], ["0x20", "Polish"], ["0x26", "Slovene"], ["0x24", "Serbian"], ["0x22", "Romanian"],
  ["0x77", "Bulgarian"], ["0x28", "Swedish"], ["0x0C", "Esperanto"], ["0x27", "Finnish"], ["0x07", "Danish"], ["0x1E", "Norwegian"],
  ["0x21", "Portuguese"], ["0x56", "Russian"], ["0x41", "Ukrainian"]];
const ANN = ["Alarm", "Traffic", "Travel", "Warning", "News", "Weather", "Event", "Special", "ProgrammeInfo", "Sports", "Finance"];
const DAB_CHANNELS = [["5A", 174.928], ["5B", 176.64], ["5C", 178.352], ["5D", 180.064], ["6A", 181.936], ["6B", 183.648], ["6C", 185.36], ["6D", 187.072],
  ["7A", 188.928], ["7B", 190.64], ["7C", 192.352], ["7D", 194.064], ["8A", 195.936], ["8B", 197.648], ["8C", 199.36], ["8D", 201.072],
  ["9A", 202.928], ["9B", 204.64], ["9C", 206.352], ["9D", 208.064], ["10A", 209.936], ["10N", 210.096], ["10B", 211.648], ["10C", 213.36], ["10D", 215.072],
  ["11A", 216.928], ["11N", 217.088], ["11B", 218.64], ["11C", 220.352], ["11D", 222.064], ["12A", 223.936], ["12N", 224.096], ["12B", 225.648], ["12C", 227.36], ["12D", 229.072],
  ["13A", 230.784], ["13B", 232.496], ["13C", 234.208], ["13D", 235.776], ["13E", 237.488], ["13F", 239.2]];

/* ============================== boot / auth ============================== */

async function boot() {
  stopPolling();
  let st;
  try { st = await api("GET", "/api/state", undefined, { quiet: true }); } catch (e) { return renderFatal(); }
  S.version = st.version; S.user = st.user; S.csrf = st.csrf; S.muxName = st.mux_name || ""; S.configured = st.configured;
  setTitle();
  if (st.setup_required) return renderSetupAccount();
  if (!S.user) return renderLogin();
  if (S.user.must_change_pw) return renderForcedPassword();
  try { S.ref = await api("GET", "/api/reference", undefined, { quiet: true }); } catch (e) { /* ignore */ }
  if (isViewer()) { try { S.caps = await api("GET", "/api/capabilities", undefined, { quiet: true }); } catch (e) { /* ignore */ } }
  renderShell();
}

function renderFatal() {
  authCard(h("div", { class: "stack" }, h("h1", null, "Cannot reach the server"),
    h("p", { class: "lead" }, "The MPBNL Multiplex WebFrontend (odr-mux-manager) service isn't responding. Check it on the server:"),
    codeBlock("sudo systemctl status odr-mux-manager --no-pager\nsudo journalctl -u odr-mux-manager -n 50 --no-pager"),
    h("p", { class: "small muted" }, "The mux and encoders keep running either way."),
    btn("Retry", { cls: "primary block", icon: "refresh", onclick: boot })), true);
}

function brand() {
  return h("div", { class: "brand" },
    h("img", { class: "brand-logo logo-dark", src: "/static/logo-dark.svg", alt: "MPBNL Multiplex WebFrontend" }),
    h("img", { class: "brand-logo logo-light", src: "/static/logo-light.svg", alt: "MPBNL Multiplex WebFrontend" }),
    S.muxName ? h("div", { class: "mux-name", title: "Multiplex" }, icon("radio"), h("span", { class: "ellipsis" }, S.muxName)) : null);
}

function authCard(children, wide = false) {
  const app = clear(document.getElementById("app"));
  const card = h("div", { class: "auth-card" + (wide ? " wide" : "") }, children);
  app.appendChild(h("div", { class: "auth" }, h("div", { class: "auth-wrap" }, brand(), card)));
  return card;
}

function renderLogin() {
  const u = inp("", { autocomplete: "username", required: true });
  const p = h("input", { type: "password", autocomplete: "current-password", required: true });
  const err = h("div", { class: "banner red hidden" });
  const submit = btn("Sign in", { cls: "primary lg block", type: "submit", icon: "login" });
  const form = h("form", { class: "stack" }, h("h1", null, "Sign in"),
    h("p", { class: "lead" }, "Monitor and manage the multiplex."), err, field("Username", u), field("Password", p), submit,
    h("p", { class: "auth-help" }, "Forgot your password? Ask an administrator to reset it."));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submit.disabled = true;
    try { await api("POST", "/api/login", { username: u.value, password: p.value }, { quiet: true }); boot(); }
    catch (ex) { put(clear(err), icon("alert"), ex.message); err.classList.remove("hidden"); p.value = ""; p.focus(); }
    finally { submit.disabled = false; }
  });
  authCard(form);
  u.focus();
}

function renderSetupAccount() {
  const token = inp(new URLSearchParams(location.search).get("token") || "", { class: "mono", autocomplete: "off" });
  const u = inp("admin", { autocomplete: "username" });
  const dn = inp("");
  const p = h("input", { type: "password", autocomplete: "new-password" });
  const p2 = h("input", { type: "password", autocomplete: "new-password" });
  const submit = btn("Create administrator", { cls: "primary lg", type: "submit" });
  const form = h("form", { class: "stack" }, h("h1", null, "Welcome"),
    h("p", { class: "muted" }, "Create the first administrator. The setup token was printed by the installer; show it again with ",
      h("code", null, "sudo odr-mux-manager setup-token"), "."),
    field("Setup token", token), h("div", { class: "grid-2" }, field("Username", u), field("Display name", dn)),
    h("div", { class: "grid-2" }, field("Password", p, { hint: "At least 10 characters." }), field("Confirm password", p2)), submit);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (p.value !== p2.value) return toast("Passwords do not match.", "error");
    submit.disabled = true;
    try {
      await api("POST", "/api/setup", { token: token.value, username: u.value, display_name: dn.value, password: p.value });
      history.replaceState(null, "", location.pathname);
      boot();
    } catch (ex) { submit.disabled = false; }
  });
  authCard(form, true);
}

function renderForcedPassword() {
  const cur = h("input", { type: "password", autocomplete: "current-password" });
  const p = h("input", { type: "password", autocomplete: "new-password" });
  const p2 = h("input", { type: "password", autocomplete: "new-password" });
  const form = h("form", { class: "stack" }, h("h1", null, "Choose a new password"),
    h("p", { class: "muted" }, "Your password was set by an administrator. Choose your own before continuing."),
    field("Current (temporary) password", cur), field("New password", p, { hint: "At least 10 characters." }), field("Confirm", p2),
    h("div", { class: "row" }, btn("Sign out", { cls: "ghost", onclick: logout }), h("span", { class: "spacer" }), btn("Save password", { cls: "primary", type: "submit" })));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (p.value !== p2.value) return toast("Passwords do not match.", "error");
    try { await api("POST", "/api/account/password", { current: cur.value, new: p.value }); toast("Password changed.", "ok"); boot(); } catch (ex) { /* toasted */ }
  });
  authCard(form);
}

async function logout() {
  try { await api("POST", "/api/logout", {}); } catch (e) { /* ignore */ }
  S.user = null; S.csrf = null; location.hash = "";
  boot();
}

/* ============================== shell ============================== */

const NAV = [
  ["MONITOR", [
    ["monitor", "On air", "activity", () => true],
    ["stations", "Stations", "grid", isViewer],
    ["ensemble", "Ensemble", "layers", isViewer],
  ]],
  ["CONFIGURE", [
    ["linking", "Linking & FI", "link", isViewer],
    ["announcements", "Announcements", "alert", isViewer],
    ["data", "Data services", "database", isViewer],
    ["dmb", "DMB", "tv", isViewer],
    ["outputs", "Mux settings", "server", isViewer],
    ["checks", "Checks", "shield", isViewer],
    ["changes", "Changes & history", "history", isViewer],
    ["files", "Config files", "code", isViewer],
  ]],
  ["ADMIN", [
    ["import", "Import / mux folder", "import", isAdmin],
    ["users", "Users", "users", isAdmin],
    ["settings", "Settings", "sliders", isAdmin],
    ["audit", "Audit log", "audit", isAdmin],
  ]],
];

let shellEls = null;

function renderShell() {
  const app = clear(document.getElementById("app"));
  const nav = h("nav", { class: "nav", "aria-label": "Main" });
  for (const [section, items] of NAV) {
    const visible = items.filter((i) => i[3]());
    if (!visible.length) continue;
    nav.appendChild(h("div", { class: "nav-section" }, section));
    for (const [key, label, ic] of visible) nav.appendChild(h("a", { href: "#/" + key, "data-key": key }, icon(ic), h("span", null, label)));
  }
  const monitor = h("div", { class: "monitor" });
  const shell = h("div", { class: "shell" + (S.collapsed ? " collapsed" : "") });
  const side = h("aside", { class: "side" }, brand(), nav,
    h("div", { class: "side-foot" }, monitor,
      h("div", { class: "user-card" },
        h("a", { class: "avatar", href: "#/account", title: "Account" }, initials(S.user.display_name || S.user.username)),
        h("div", { class: "who" }, h("b", { class: "ellipsis" }, S.user.display_name || S.user.username), h("span", null, ROLE_LABEL[S.user.role])),
        themeToggle(), iconBtn("logout", "Sign out", logout)),
      h("button", { class: "collapse-btn", onclick: () => {
        S.collapsed = !S.collapsed; shell.classList.toggle("collapsed", S.collapsed);
        try { localStorage.setItem("odrmux.collapsed", S.collapsed ? "1" : "0"); } catch (e) { /* ignore */ }
      } }, icon("chevronsLeft"), h("span", null, "Collapse"))));
  const crumbs = h("div", { class: "crumbs" });
  const pending = h("div", { class: "row" });
  const content = h("div", { class: "content" });
  const main = h("main", { class: "main" },
    h("div", { class: "topbar" }, h("span", { class: "mobile-only" }, iconBtn("menu", "Menu", () => shell.classList.toggle("mobile-nav"))), crumbs, h("span", { class: "spacer" }), pending),
    content);
  put(shell, side, main);
  app.appendChild(shell);
  shellEls = { nav, monitor, crumbs, pending, content, shell };
  side.addEventListener("click", (e) => { if (e.target.closest("a")) shell.classList.remove("mobile-nav"); });
  window.onhashchange = route;
  route();
  refreshStatus();
}

function setCrumbs(...parts) {
  const c = clear(shellEls.crumbs);
  parts.forEach((p, i) => {
    if (i) c.appendChild(h("span", null, "/"));
    c.appendChild(i === parts.length - 1 ? h("b", null, p.label || p) : h("a", { href: p.href }, p.label));
  });
}

function route() {
  if (!shellEls) return;
  if (S.skipRoute) { S.skipRoute = false; return; }
  const dirty = liveDirty();
  if (dirty.length && S.currentHash != null && location.hash !== S.currentHash) {
    const target = location.hash;
    S.skipRoute = true;            // putting the old URL back fires hashchange: don't re-render for it
    location.hash = S.currentHash;
    const go = () => { DIRTY.clear(); location.hash = target; };
    const m = modal({ title: "Unsaved changes",
      body: h("p", null, "You changed fields on this page without saving them. Save them to the draft first, or throw them away?"),
      foot: [btn("Stay here", { onclick: () => m.close() }),
        btn("Discard", { cls: "danger ghost", onclick: () => { m.close(); go(); } }),
        btn("Save and continue", { cls: "primary", onclick: async () => {
          m.close();
          for (const b of dirty) { try { await b._save(); } catch (e) { /* toasted */ } }
          go();
        } })] });
    return;
  }
  DIRTY.clear();
  S.currentHash = location.hash;
  stopMon();
  closeAllModals();
  const parts = (location.hash.replace(/^#\/?/, "") || "monitor").split("/");
  const key = parts[0];
  shellEls.nav.querySelectorAll("a").forEach((a) => a.classList.toggle("active", a.dataset.key === key));
  // Each render gets its own container. If a page is rendered again before the previous (async)
  // render finished - e.g. a save that changes the URL *and* re-routes - the old render writes into
  // a detached element instead of duplicating everything on screen.
  const content = h("div", { class: "page" });
  trackDirty(content);
  clear(shellEls.content).appendChild(content);
  const pages = { monitor: pageMonitor, stations: pageStations, ensemble: pageEnsemble, linking: pageLinking, announcements: pageAnnouncements,
    data: pageData, dmb: pageDmb, outputs: pageOutputs, checks: pageChecks, changes: pageChanges, files: pageFiles,
    import: pageImport, users: pageUsers, settings: pageSettings, audit: pageAudit, account: pageAccount };
  let fn = pages[key] || pageMonitor;
  if (!isViewer() && key !== "account") fn = pageMonitor;
  if (!S.configured && isViewer() && !["import", "users", "settings", "audit", "account"].includes(key)) fn = isAdmin() ? pageImport : pageNotConfigured;
  Promise.resolve(fn(content, parts.slice(1))).catch((e) => {
    if (!(e instanceof ApiError)) { console.error(e); toast("Something went wrong rendering this page.", "error"); }
  });
  shellEls.content.parentElement.scrollTop = 0;
}

function pageNotConfigured(root) {
  setCrumbs("Not set up");
  put(root, h("div", { class: "empty" }, h("h3", null, "No mux imported yet"), h("p", null, "An administrator has to point the manager at the mux folder first.")));
}

function stopPolling() { if (S.pollTimer) clearTimeout(S.pollTimer); S.pollTimer = null; stopMon(); }
function stopMon() { if (S.monTimer) clearTimeout(S.monTimer); S.monTimer = null; }

async function refreshStatus() {
  if (S.pollTimer) clearTimeout(S.pollTimer);
  if (!S.user || !shellEls) return;
  try {
    if (isViewer() && S.configured) {
      const d = await api("GET", "/api/draft", undefined, { quiet: true });
      renderPending(d);
    }
  } catch (e) { /* ignore */ }
  S.pollTimer = setTimeout(refreshStatus, 8000);
}

function renderPending(d) {
  const p = clear(shellEls.pending);
  if (d && d.pending) {
    p.appendChild(h("div", { class: "pending" }, icon("alert"), h("span", null, d.stale ? "Unapplied changes (files changed on disk!)" : "Unapplied changes"),
      btn("Review & apply", { cls: "primary sm", icon: "zap", onclick: () => { location.hash = "#/changes"; } })));
  } else if (S.configured) {
    p.appendChild(h("div", { class: "pending ok" }, icon("check"), "Config matches what's running"));
  }
}
const pokeStatus = () => refreshStatus();

/* ============================== shared widgets ============================== */

function codecBadge(c) { return c ? h("span", { class: "codec " + c }, CODEC_LABEL[c] || c) : null; }

// One plain colour per station: picked from its id (so it doesn't change between refreshes) and
// never the same as the segment next to it.
const STATION_COLOURS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#14b8a6", "#ec4899", "#eab308",
  "#06b6d4", "#84cc16", "#6366f1", "#f97316", "#10b981", "#e11d48", "#8b5cf6", "#0ea5e9"];
function hashStr(t) { let x = 2166136261; for (const c of String(t)) { x ^= c.charCodeAt(0); x = Math.imul(x, 16777619); } return x >>> 0; }
function stationColours(list) {
  const out = {};
  let prev = -1;
  for (const s of list) {
    let i = hashStr(s.id) % STATION_COLOURS.length;
    if (i === prev) i = (i + 1) % STATION_COLOURS.length;
    out[s.id] = STATION_COLOURS[i];
    prev = i;
  }
  return out;
}
S.colours = {};
// the CSP forbids inline style attributes, so set the colour through the CSSOM
function stDot(id) { const d = h("i", { class: "st-dot" }); d.style.background = S.colours[id] || "var(--border-strong)"; return d; }

function cuBar(total, segs, draftUsed, opts = {}) {
  const used = segs.reduce((a, s) => a + s.cu, 0);
  const colours = stationColours(segs);
  Object.assign(S.colours, colours);
  const bar = h("div", { class: "cubar" + (opts.big ? " big" : "") });
  // one floating tooltip per bar, centred horizontally on the mouse pointer
  const tip = h("div", { class: "cu-tip" });
  const track = h("div", { class: "cu-track" }, tip, bar);
  const showTip = (ev, parts) => {
    clear(tip).append(...parts);
    tip.classList.add("on");
    const r = track.getBoundingClientRect();
    const half = tip.offsetWidth / 2;
    const x = Math.max(half, Math.min(r.width - half, ev.clientX - r.left));
    tip.style.left = x + "px";
  };
  bar.addEventListener("mouseleave", () => tip.classList.remove("on"));
  const sep = () => h("span", { class: "cu-tip-sep" });
  for (const s of segs) {
    const data = s.kind !== "audio";
    const seg = h("i", { class: "seg" + (data ? " data" : "") });
    seg.style.width = (100 * s.cu / total) + "%";
    seg.style.setProperty("--c", colours[s.id]);
    const sid = String(s.id || "").startsWith("sub:") ? "" : s.id;
    const parts = () => [h("span", { class: "cu-tip-k" }, s.kind === "data" ? "Data:" : "Service:"), h("b", null, s.label || "Unnamed"), sep(),
      h("span", { class: "cu-tip-cu" }, `${s.cu} CU`), sep(), h("span", { class: "cu-tip-k" }, "SID:"), h("span", { class: "mono" }, sid ? "0x" + sid : "")];
    seg.addEventListener("mousemove", (ev) => showTip(ev, parts()));
    if (opts.big && s.cu / total > 0.045) seg.appendChild(h("span", { class: "seg-label" }, s.shortlabel || s.label || ""));
    bar.appendChild(seg);
  }
  if (draftUsed != null && draftUsed !== used) {
    const diff = draftUsed - used;
    const seg = h("i", { class: "seg pending" + (diff < 0 ? " neg" : "") });
    seg.style.width = (100 * Math.abs(diff) / total) + "%";
    if (diff < 0) seg.style.marginLeft = (-100 * Math.abs(diff) / total) + "%";
    seg.addEventListener("mousemove", (ev) => showTip(ev, [h("span", { class: "cu-tip-k" }, "Unapplied:"), h("b", null, `${diff > 0 ? "+" : ""}${diff} CU`)]));
    bar.appendChild(seg);
  }
  if (used < total) {
    // free capacity: takes the rest of the bar, and gives way when tiny segments need their minimum width
    const free = h("i", { class: "seg free" });
    free.addEventListener("mousemove", (ev) => showTip(ev, [h("span", { class: "cu-tip-k" }, "Free:"), h("span", { class: "cu-tip-cu" }, `${total - used} CU`)]));
    bar.appendChild(free);
  }
  const over = Math.max(used, draftUsed || 0) > total;
  return h("div", { class: "cu-wrap" + (over ? " over" : "") },
    h("div", { class: "row" }, icon("activity"), h("b", null, "Capacity (CU)"), h("span", { class: "spacer" }),
      draftUsed != null && draftUsed !== used ? h("span", { class: "chip amber" }, `${draftUsed} after apply`) : null,
      h("span", { class: "cu-num" }, h("b", null, used), ` / ${total}`)),
    track,
    h("div", { class: "row small muted" }, h("span", { class: "lg-key solid" }), "Station", h("span", { class: "lg-key data" }), "Data service",
      h("span", { class: "lg-key pending" }), "Unapplied", h("span", { class: "spacer" }), `${total - used} CU free`));
}

function dbToPct(db) { if (db == null) return 0; return Math.max(0, Math.min(100, (db + 60) / 60 * 100)); }
function levelMeter(levels, big = false) {
  const wrap = h("div", { class: "lvl" + (big ? " big" : "") });
  for (const ch of ["l", "r"]) {
    const v = levels ? levels[ch] : null;
    const bar = h("div", { class: "lvl-bar" });
    const fill = h("i", { class: "lvl-fill" + (v != null && v > -3 ? " hot" : v != null && v > -12 ? " warm" : "") });
    fill.style.width = dbToPct(v) + "%";
    bar.appendChild(fill);
    if (levels && levels[ch + "_slow"] != null) {
      const pk = h("i", { class: "lvl-peak" });
      pk.style.left = dbToPct(levels[ch + "_slow"]) + "%";
      bar.appendChild(pk);
    }
    wrap.appendChild(h("div", { class: "lvl-row" }, h("span", { class: "lvl-ch" }, ch.toUpperCase()), bar,
      h("span", { class: "lvl-db mono" }, v == null ? "—" : (v <= -89 ? "-∞" : v.toFixed(0)))));
  }
  return wrap;
}

function procDot(p, label) {
  if (!p) return null;
  const ok = p.state === "RUNNING";
  return h("span", { class: "chip " + (ok ? "green" : (p.state === "STARTING" || p.state === "BACKOFF" ? "amber" : "red")), title: p.description || p.state },
    h("i", { class: "dot " + (ok ? "green" : "red") }), label);
}

/* ============================== monitor (main page) ============================== */

let monFilter = { q: "", tab: "all" };

async function pageMonitor(root, parts) {
  setCrumbs("On air");
  if (!S.configured) return isAdmin() ? pageImport(root) : pageNotConfigured(root);
  let ov = await api("GET", "/api/overview");
  Object.assign(S.colours, stationColours(ov.cu_segments || ov.stations));
  const head = h("div");
  const grid = h("div", { class: "mon-grid" });
  const search = h("input", { type: "search", placeholder: "Search stations", value: monFilter.q, "aria-label": "Search" });
  const seg = h("div", { class: "segmented" });
  const tabs = [["all", "All"], ["issues", "Issues"], ["audio", "Audio"], ["data", "Data"]];
  const drawSeg = () => { clear(seg); for (const [k, l] of tabs) seg.appendChild(h("button", { class: monFilter.tab === k ? "on" : "", onclick: () => { monFilter.tab = k; drawSeg(); draw(); } }, l)); };
  let snap = { stations: {} };
  const cards = {};

  const drawHead = () => {
    const e = ov.ensemble || {};
    const st = h("div", { class: "row wrap" });
    if (snap.dabmux) st.appendChild(h("span", { class: "chip " + (snap.dabmux.ok ? "green" : "red"), title: snap.dabmux.endpoint }, h("i", { class: "dot " + (snap.dabmux.ok ? "green" : "red") }), snap.dabmux.ok ? "odr-dabmux up" : "odr-dabmux not answering"));
    if (snap.supervisor) st.appendChild(h("span", { class: "chip " + (snap.supervisor.ok ? "green" : "amber"), title: snap.supervisor.error || "" }, h("i", { class: "dot " + (snap.supervisor.ok ? "green" : "amber") }), snap.supervisor.ok ? "supervisor connected" : "supervisor unavailable"));
    if (snap.onair) st.appendChild(h("span", { class: "chip " + (snap.onair.ok ? "green" : "muted"), title: snap.onair.source || "" }, icon("radio"), snap.onair.ok ? "decoding mux output" : "on-air decoder idle"));
    if (ov.issues && ov.issues.error) st.appendChild(h("a", { class: "chip red", href: "#/checks" }, icon("alert"), `${ov.issues.error} config error${ov.issues.error > 1 ? "s" : ""}`));
    put(clear(head),
      h("div", { class: "page-head" }, h("div", null, h("h1", null, e.label || "Multiplex"),
        h("p", null, [e.id ? `EId ${e.id}` : null, e.ecc ? `ECC ${e.ecc}` : null, `${ov.stations.length} station${ov.stations.length === 1 ? "" : "s"}`].filter(Boolean).join(" · "))),
        h("span", { class: "spacer" }), st),
      isViewer() && ov.cu_segments ? h("div", { class: "card card-pad" }, cuBar(ov.cu_total, ov.cu_segments, ov.cu_draft, { big: true })) : null);
  };

  const problems = (s) => ((snap.stations[s.id] || {}).alerts || []);
  const draw = () => {
    clear(grid);
    const q = monFilter.q.toLowerCase();
    let list = ov.stations.filter((s) => {
      if (q && ![s.label, s.shortlabel, s.id, s.ptag].some((x) => (x || "").toLowerCase().includes(q))) return false;
      if (monFilter.tab === "issues") return problems(s).length > 0;
      if (monFilter.tab === "audio") return s.kind === "audio";
      if (monFilter.tab === "data") return s.kind !== "audio";
      return true;
    });
    // stations with problems float to the top
    list = list.slice().sort((a, b) => (problems(b).some((p) => p.sev === "error") - problems(a).some((p) => p.sev === "error")) || (a.position - b.position));
    if (!ov.stations.length) grid.appendChild(h("div", { class: "empty span-all" }, h("h3", null, isViewer() ? "No stations" : "No stations assigned to you"),
      h("p", null, isViewer() ? "Add stations under Stations." : "Ask an administrator to give you access to your station.")));
    else if (!list.length) grid.appendChild(h("div", { class: "empty span-all" }, "Nothing matches."));
    for (const s of list) { cards[s.id] = monCard(s); grid.appendChild(cards[s.id].el); cards[s.id].update(snap.stations[s.id]); }
  };
  search.addEventListener("input", debounce(() => { monFilter.q = search.value; draw(); }, 120));
  drawSeg();
  put(root, head, h("div", { class: "section-gap" }), h("div", { class: "row wrap" }, h("div", { class: "search" }, icon("search"), search), seg),
    h("div", { class: "section-gap" }), grid);
  drawHead();
  draw();
  let tick = 0;
  const poll = async () => {
    try {
      snap = await api("GET", "/api/monitor", undefined, { quiet: true });
      const before = JSON.stringify(ov.stations.map((s) => s.id));
      if (++tick % 15 === 0) { ov = await api("GET", "/api/overview", undefined, { quiet: true }); }
      if (tick === 1 || tick % 15 === 0) drawHead();
      if (monFilter.tab === "issues" || JSON.stringify(ov.stations.map((s) => s.id)) !== before) draw();
      for (const s of ov.stations) if (cards[s.id]) cards[s.id].update(snap.stations[s.id]);
    } catch (e) { /* offline */ }
    if (location.hash.replace(/^#\/?/, "").split("/")[0] in { "": 1, monitor: 1 }) S.monTimer = setTimeout(poll, 1000);
  };
  poll();
  if (parts[0]) setTimeout(() => { const s = ov.stations.find((x) => x.id === parts[0]); if (s) monDetail(s, () => snap.stations[s.id]); }, 200);
}

function monCard(s) {
  const meters = h("div");
  const dls = h("div", { class: "dls ellipsis2" });
  const slide = h("div", { class: "slide-thumb" });
  const chips = h("div", { class: "row wrap tight" });
  const alerts = h("div", { class: "row wrap tight" });
  const el = h("button", { class: "station-card mon-card", type: "button", onclick: () => monDetail(s, () => last) },
    h("div", { class: "sc-head" },
      h("div", { class: "titles" }, h("h3", { class: "ellipsis" }, stDot(s.id), s.label || "(no label)"),
        h("div", { class: "sub" }, s.kind === "audio" ? [codecBadge(s.codec), ` ${s.bitrate} kbps`, s.protection ? ` · ${s.protection}` : "", s.cu != null ? ` · ${s.cu} CU` : ""] : [h("span", { class: "codec data" }, s.kind.toUpperCase()), ` ${s.bitrate} kbps`])),
      h("span", { class: "pos mono" }, s.ptag || ("#" + s.position))),
    s.kind === "audio" ? h("div", { class: "mon-body" }, h("div", { class: "grow stack tight" }, meters, dls), slide) : h("div", { class: "small muted" }, s.inputuri || ""),
    h("div", { class: "sc-foot" }, chips, alerts));
  let last = null;
  const update = (d) => {
    last = d;
    if (s.kind === "audio") put(clear(meters), levelMeter(d && d.levels));
    const t = d && (d.onair && d.onair.dls ? d.onair.dls : (d.dls && d.dls.text));
    clear(dls);
    const dp = d && d.dls && d.dls.dlplus;
    if (dp && (d.dls.artist || d.dls.title)) {
      dls.append(h("span", { class: "dlp", title: "DL Plus" }, "DL+"), " ",
        d.dls.artist ? h("b", null, d.dls.artist) : null, d.dls.artist && d.dls.title ? " – " : null, d.dls.title || "");
    } else dls.append(t || (s.feed === "external" ? "External feed" : "—"));
    dls.title = t || "";
    clear(slide);
    const sl = d && d.slides;
    if (d && d.onair && d.onair.slide) slide.appendChild(h("img", { src: `/api/monitor/${s.id}/onair-slide?t=${d.onair.slide.ts}`, alt: "On-air slide", loading: "lazy" }));
    else if (sl && sl.items && sl.items.length) slide.appendChild(h("img", { src: `/api/monitor/${s.id}/slide/${encodeURIComponent(sl.items[0].name)}`, alt: "", loading: "lazy" }));
    else slide.appendChild(icon("image"));
    if (sl && sl.count) slide.appendChild(h("span", { class: "slide-count" }, `${sl.count}`));
    clear(chips);
    if (s.feed === "external") chips.appendChild(h("span", { class: "chip blue" }, icon("globe"), "external"));
    if (d) { for (const [k, l] of [["audio", "audio"], ["pad", "PAD"], ["dmb", "DMB encoder"]]) { const c = procDot(d[k], l); if (c) chips.appendChild(c); } }
    if (d && d.input_state && String(d.input_state).startsWith("Silent")) chips.appendChild(h("span", { class: "chip amber" }, "Silent"));
    clear(alerts);
    for (const a of (d && d.alerts) || []) alerts.appendChild(h("span", { class: "chip " + (a.sev === "error" ? "red" : "amber") }, icon("alert"), a.msg));
    el.classList.toggle("problem", !!(d && d.alerts && d.alerts.some((a) => a.sev === "error")));
  };
  return { el, update };
}

function monDetail(s, getSnap) {
  const body = h("div", { class: "stack" });
  const logBox = h("div");
  let timer = null;
  const draw = () => {
    const d = getSnap() || {};
    const dlsTxt = d.onair && d.onair.dls ? d.onair.dls : (d.dls && d.dls.text);
    put(clear(body),
      h("div", { class: "row wrap" }, codecBadge(s.codec), h("span", null, `${s.bitrate} kbps`), s.protection ? h("span", { class: "muted" }, s.protection) : null,
        h("span", { class: "spacer" }), procDot(d.audio, "audio encoder"), procDot(d.pad, "PAD encoder")),
      s.kind === "audio" ? levelMeter(d.levels, true) : null,
      d.levels ? h("div", { class: "small muted" }, `Levels from ${d.levels.src === "dabmux" ? "odr-dabmux input" : "the encoder"}` +
        (d.input_state ? ` · odr-dabmux state ${d.input_state}` + (String(d.input_state).startsWith("Unstable") && !d.glitching ? " (it keeps this for 30 min after glitches; none in the last minute)" : "") : "") +
        (d.buffer && d.buffer.min != null ? ` · buffer ${d.buffer.min}–${d.buffer.max} frames, ${d.buffer.underruns || 0} underruns, ${d.buffer.overruns || 0} overruns` : "")) : null,
      h("div", { class: "card card-pad" }, h("div", { class: "small muted" }, d.onair && d.onair.dls ? "DLS on air" : "DLS (from the encoder's text file)"), h("div", { class: "dls big" }, dlsTxt || "—"),
        d.dls && d.dls.dlplus && d.dls.dlplus.items.length ? h("div", { class: "row wrap tight dlp-items" }, h("span", { class: "dlp" }, "DL+"),
          d.dls.dlplus.items.map((it) => h("span", { class: "chip" }, h("span", { class: "muted" }, it.name + ": "), it.text)),
          d.dls.dlplus.running ? null : h("span", { class: "chip" }, "item not running")) : null,
        d.dls && d.dls.mtime ? h("div", { class: "small muted" }, "Updated " + fmtAgo(d.dls.mtime)) : null),
      d.onair && d.onair.slide ? h("div", { class: "stack tight" }, h("div", { class: "small muted" }, "Slide on air"),
        h("img", { class: "onair-slide", src: `/api/monitor/${s.id}/onair-slide?t=${d.onair.slide.ts}`, alt: "On-air slide" })) : null,
      d.slides && d.slides.items ? h("div", { class: "stack tight" },
        h("div", { class: "small muted" }, `${d.slides.count} slide${d.slides.count === 1 ? "" : "s"} in the folder` + (d.slides.sleep ? `, each shown ~${d.slides.sleep}s` : "")),
        h("div", { class: "slide-grid" }, d.slides.items.map((x) => h("figure", null, h("img", { src: `/api/monitor/${s.id}/slide/${encodeURIComponent(x.name)}`, alt: x.name, loading: "lazy" }), h("figcaption", { class: "ellipsis" }, x.name))))) :
        (d.slides && d.slides.missing ? h("div", { class: "banner amber" }, icon("alert"), "The slide folder does not exist or can't be read.") : null),
      d.stats_error ? h("div", { class: "small muted" }, `Stats socket: ${d.stats_error}`) : null,
      logBox);
  };
  draw();
  const loadLog = async (which) => {
    try { const r = await api("GET", `/api/monitor/${s.id}/log?which=${which}`); put(clear(logBox), h("div", { class: "code log" }, r.text || "(empty)")); } catch (e) { /* toasted */ }
  };
  const restart = async (which) => {
    if (!(await confirmDialog(`Restart the ${which === "both" ? "audio and PAD encoders" : which === "pad" ? "PAD encoder" : "audio encoder"} for ${s.label}? There will be a short gap on air.`, { okText: "Restart", danger: true }))) return;
    try { await api("POST", `/api/monitor/${s.id}/restart`, { which }); toast("Restarted.", "ok"); } catch (e) { /* toasted */ }
  };
  const foot = [];
  if (isViewer() && s.audio_program) foot.push(btn("Audio log", { cls: "ghost", onclick: () => loadLog("audio") }));
  if (isViewer() && s.pad_program) foot.push(btn("PAD log", { cls: "ghost", onclick: () => loadLog("pad") }));
  if (isViewer()) foot.push(btn("Edit station", { icon: "edit", onclick: () => { m.close(); location.hash = `#/stations/${s.id}`; } }));
  if (isEditor() && s.audio_program) foot.push(btn("Restart encoders", { cls: "danger", icon: "power", onclick: () => restart("both") }));
  const m = modal({ title: s.label || s.id, body, foot, wide: true, onclose: () => clearInterval(timer) });
  timer = setInterval(draw, 1000);
}

/* ============================== stations ============================== */

async function pageStations(root, parts) {
  if (parts[0] === "new") return stationNew(root);
  if (parts[0]) return stationDetail(root, decodeURIComponent(parts[0]), parts[1] || "service");
  setCrumbs("Stations");
  const d = await api("GET", "/api/stations");
  const audio = d.stations.filter((s) => s.kind !== "data");
  let order = audio.map((s) => s.id);
  let removed = new Set();
  let mode = "keep";
  const byId = Object.fromEntries(d.stations.map((s) => [s.id, s]));
  const tbody = h("tbody");
  const changed = () => removed.size > 0 || order.join() !== audio.map((s) => s.id).join();
  const actions = h("div", { class: "row" });
  const draw = () => {
    clear(tbody);
    order.forEach((id, i) => {
      const s = byId[id];
      const rm = removed.has(id);
      const tr = h("tr", { class: "click" + (rm ? " removed" : "") },
        h("td", { class: "mono muted" }, i + 1),
        h("td", null, h("b", null, s.label || "(no label)"), h("div", { class: "small muted mono" }, `${s.service_uid || ""} · SId ${s.id}`)),
        h("td", null, codecBadge(s.codec), " ", `${s.bitrate}k`),
        h("td", { class: "mono" }, s.protection), h("td", { class: "mono" }, s.cu),
        h("td", null, s.feed === "local" ? h("span", { class: "chip green" }, "local") : s.feed === "external" ? h("span", { class: "chip blue" }, icon("globe"), "external") : h("span", { class: "chip" }, s.feed)),
        h("td", { class: "mono small" }, s.port || ""), h("td", { class: "mono small" }, s.ptag || ""),
        isEditor() ? h("td", { class: "nowrap", onclick: (e) => e.stopPropagation() },
          iconBtn("arrowUp", "Move up", () => { if (i > 0) { [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); } }),
          iconBtn("arrowDown", "Move down", () => { if (i < order.length - 1) { [order[i + 1], order[i]] = [order[i], order[i + 1]]; draw(); } }),
          iconBtn(rm ? "refresh" : "trash", rm ? "Keep" : "Remove", () => { rm ? removed.delete(id) : removed.add(id); draw(); })) : null);
      tr.addEventListener("click", () => { location.hash = `#/stations/${encodeURIComponent(id)}`; });
      tbody.appendChild(tr);
    });
    clear(actions);
    if (isEditor() && changed()) {
      actions.appendChild(h("div", { class: "segmented" }, [["keep", "Keep numbers"], ["renumber", "Close gaps (renumber)"]].map(([k, l]) =>
        h("button", { class: mode === k ? "on" : "", onclick: () => { mode = k; draw(); } }, l))));
      actions.appendChild(btn("Undo", { cls: "ghost", onclick: () => { order = audio.map((s) => s.id); removed = new Set(); draw(); } }));
      actions.appendChild(btn("Preview changes", { cls: "primary", icon: "eye", onclick: preview }));
    }
  };
  const preview = async () => {
    const body = { order, remove: [...removed], mode };
    const pl = await api("POST", "/api/stations/plan", body);
    const affected = pl.stations.filter((s) => s.changes.length || s.old_position !== s.new_position);
    const content = h("div", { class: "stack" },
      pl.removed.length ? h("div", { class: "banner red" }, icon("trash"), h("div", { class: "grow" }, h("b", null, "Removing: "), pl.removed.map((r) => r.label).join(", "))) : null,
      mode === "renumber" && affected.some((a) => a.changes.length) ? h("div", { class: "banner amber" }, icon("alert"), h("div", { class: "grow" },
        h("b", null, `${affected.filter((a) => a.changes.length).length} station(s) get new numbers. `),
        "Anything outside the manager that points at the old numbers (scripts writing DLS/slides into mot folders, stats readers, firewall rules, remote-control scripts) has to be repointed. Every affected station is listed below.")) : null,
      affected.length ? h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, h("th", null, "Station"), h("th", null, "Position"), h("th", null, "Changes"))),
        h("tbody", null, affected.map((a) => h("tr", null, h("td", null, a.label), h("td", { class: "mono" }, a.old_position === a.new_position ? a.new_position : `${a.old_position} → ${a.new_position}`),
          h("td", { class: "small" }, a.changes.length ? a.changes.map((c) => h("div", { class: "mono" }, `${c.what}: ${c.old} → ${c.new}`)) : h("span", { class: "muted" }, "order only"))))))) : null,
      pl.impact.length ? h("div", { class: "stack tight" }, h("h3", null, "What to repoint outside the manager"),
        pl.impact.map((it) => h("div", { class: "card card-pad impact" + (it.removed ? " removed" : "") }, h("b", null, (it.removed ? "Removed: " : "") + it.label),
          h("ul", null, it.items.map((x) => h("li", null, x)))))) : null,
      h("p", { class: "small muted" }, "Nothing is changed on air until you Apply. MOT folders are renamed on Apply (two-step, so nothing gets overwritten); a backup is taken first."));
    const m = modal({ title: "Review station changes", body: content, wide: true,
      foot: [btn("Cancel", { onclick: () => m.close() }), btn("Stage these changes", { cls: "primary", onclick: async () => {
        try { await api("POST", "/api/stations/reorder", body); m.close(); toast("Staged. Review and apply under Changes.", "ok"); pokeStatus(); route(); } catch (e) { /* toasted */ }
      } })] });
  };
  draw();
  const data = d.stations.filter((s) => s.kind === "data");
  put(root,
    h("div", { class: "page-head" }, h("div", null, h("h1", null, "Stations"), h("p", null, `${audio.length} station${audio.length === 1 ? "" : "s"} · ${d.cu_used}/${d.cu_total} CU after apply`)),
      h("span", { class: "spacer" }), isEditor() ? btn("Add station", { cls: "primary", icon: "plus", onclick: () => { location.hash = "#/stations/new"; } }) : null),
    h("div", { class: "row" }, actions),
    h("div", { class: "section-gap" }),
    h("div", { class: "card" }, h("div", { class: "table-wrap" }, h("table", null,
      h("thead", null, h("tr", null, ["#", "Station", "Codec", "Protection", "CU", "Feed", "Port", "Tag", isEditor() ? "" : null].filter((x) => x !== null).map((x) => h("th", null, x)))), tbody))),
    d.orphans && d.orphans.length ? h("div", { class: "banner amber mt" }, icon("alert"), `Services without a component (not broadcast): ${d.orphans.join(", ")}`) : null,
    data.length ? h("p", { class: "small muted mt" }, `${data.length} data service(s) are managed under `, h("a", { href: "#/data" }, "Data services"), ".") : null);
}

function inputOptions() {
  const avail = (S.caps && S.caps.inputs) || ["gstreamer", "vlc", "alsa", "jack", "file"];
  const all = [["gstreamer", "GStreamer (URL)"], ["vlc", "VLC (URL)"], ["alsa", "ALSA device"], ["jack", "JACK"], ["file", "File / FIFO"]];
  return all.map(([k, l]) => [k, l + (S.caps && S.caps.audioenc && !avail.includes(k) ? " - not in this odr-audioenc" : "")]);
}

function codecOptions() { return [["hev2", "DAB+ HE-AAC v2"], ["he", "DAB+ HE-AAC"], ["aaclc", "DAB+ AAC-LC"], ["auto", "DAB+ (encoder picks by bitrate)"], ["mp2", "DAB (MP2)"]]; }

function protectionPicker(type, bitrate, profile, level, onchange) {
  const uep = (S.ref && S.ref.uep) || [];
  const wrap = h("div", { class: "grid-3" });
  const prof = sel(profile || (type === "audio" ? "UEP" : "EEP_A"), [["UEP", "UEP (MP2 only)"], ["EEP_A", "EEP-A"], ["EEP_B", "EEP-B (bitrate ÷ 32)"]]);
  const lvl = sel(level || 3, [[1, "1 (strongest)"], [2, "2"], [3, "3"], [4, "4"], [5, "5 (UEP only, weakest)"]]);
  const cuOut = h("div", { class: "stat" }, h("span", null, "Capacity"), h("b", null, "—"));
  const calc = () => {
    const br = parseInt(bitrate()), l = parseInt(lvl.value), p = prof.value;
    let cu = 0, note = "";
    if (p === "UEP") {
      const e = uep.find((x) => x.bitrate === br && x.level === l);
      if (e) cu = e.cu; else { note = "no UEP at this bitrate/level - dabmux falls back to EEP-A"; cu = { 1: br * 12 / 8, 2: br, 3: br * 6 / 8, 4: br / 2 }[l] || 0; }
    } else if (p === "EEP_A") cu = { 1: br * 12 / 8, 2: br, 3: br * 6 / 8, 4: br / 2 }[l] || 0;
    else { cu = { 1: br * 27 / 32, 2: br * 21 / 32, 3: br * 18 / 32, 4: br * 15 / 32 }[l] || 0; if (br % 32) note = "EEP-B needs a multiple of 32 kbps"; }
    put(clear(cuOut), h("span", null, "Capacity"), h("b", null, `${Math.floor(cu)} CU`), note ? h("span", { class: "small amber-text" }, note) : null);
    onchange && onchange();
  };
  prof.addEventListener("change", calc); lvl.addEventListener("change", calc);
  put(wrap, field("Protection profile", prof), field("Level", lvl), cuOut);
  setTimeout(calc);
  return { el: wrap, prof, lvl, calc };
}

async function stationNew(root) {
  setCrumbs({ label: "Stations", href: "#/stations" }, "New station");
  const label = inp("", { maxlength: 16 }), short = inp("", { maxlength: 8 }), sid = inp("", { class: "mono", placeholder: "0x2491" }), ecc = inp("", { class: "mono", placeholder: "(ensemble ECC)" });
  const pty = sel(10, PTY.map((p, i) => [i, `${i} ${p}`])), lang = sel("0x09", LANGS);
  const codec = sel("hev2", codecOptions());
  const bitrate = inp("64", { type: "number", min: 8, max: 384, step: 8 });
  const prot = protectionPicker("dabplus", () => bitrate.value, "EEP_A", 3);
  const feed = sel("local", [["local", "Local encoder (create odr-audioenc + odr-padenc)"], ["external", "External feed (someone else sends EDI/ZMQ)"]]);
  const ikind = sel((S.caps && S.caps.inputs && S.caps.inputs[0]) || "gstreamer", inputOptions());
  const iurl = inp("", { placeholder: "https://stream.example/live.mp3" });
  const psy = sel(1, [[0, "0"], [1, "1 (default)"], [2, "2"], [3, "3"]]);
  const extProto = sel("edi", [["edi", "EDI (tcp)"], ["zmq", "ZMQ"]]);
  const extPort = inp("", { type: "number", placeholder: "auto" });
  const psyField = field("MP2 psychoacoustic model (--dabpsy)", psy, { hint: "0-3; 1 is the encoder default." });
  const localBox = h("div", { class: "stack" }, h("div", { class: "grid-2" }, field("Input", ikind), field("Source", iurl)), psyField);
  const extBox = h("div", { class: "grid-2" }, field("Protocol", extProto), field("Listen port", extPort, { hint: "The remote encoder sends to this port on this server." }));
  const sync = () => {
    localBox.classList.toggle("hidden", feed.value !== "local"); extBox.classList.toggle("hidden", feed.value !== "external");
    psyField.classList.toggle("hidden", codec.value !== "mp2");
    if (codec.value === "mp2" && prot.prof.value !== "UEP") { prot.prof.value = "UEP"; prot.calc(); }
    if (codec.value !== "mp2" && prot.prof.value === "UEP") { prot.prof.value = parseInt(bitrate.value) % 32 ? "EEP_A" : "EEP_B"; prot.calc(); }
  };
  [feed, codec].forEach((x) => x.addEventListener("change", sync));
  bitrate.addEventListener("input", () => prot.calc());
  sync();
  const save = async () => {
    const body = { label: label.value, shortlabel: short.value, sid: sid.value, ecc: ecc.value || undefined, pty: parseInt(pty.value), language: lang.value || undefined,
      codec: codec.value, bitrate: parseInt(bitrate.value), protection: parseInt(prot.lvl.value), profile: prot.prof.value === "UEP" ? undefined : prot.prof.value, feed: feed.value };
    if (feed.value === "local") body.encoder = { input_kind: ikind.value, input: iurl.value, dabpsy: codec.value === "mp2" ? parseInt(psy.value) : undefined };
    else body.external = { proto: extProto.value, port: extPort.value ? parseInt(extPort.value) : undefined };
    try { const r = await api("POST", "/api/stations", body); toast("Station staged. Apply to put it on air.", "ok"); pokeStatus(); location.hash = `#/stations/${encodeURIComponent(r.station)}`; } catch (e) { /* toasted */ }
  };
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "New station"), h("p", null, "Creates the service, subchannel and component - and the encoders when it is fed locally."))),
    h("div", { class: "card card-pad stack" },
      h("h3", null, "Service"),
      h("div", { class: "grid-3" }, field("Label", label, { max: 16 }), field("Short label", short, { max: 8, hint: "Characters of the label, in order." }), field("Service id (SId)", sid)),
      h("div", { class: "grid-3" }, field("ECC", ecc), field("Programme type", pty), field("Language", lang)),
      h("h3", null, "Audio & capacity"),
      h("div", { class: "grid-2" }, field("Codec", codec), field("Bitrate (kbps)", bitrate)), prot.el,
      h("h3", null, "Feed"), field("Fed by", feed), localBox, extBox,
      h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Cancel", { cls: "ghost", onclick: () => history.back() }), btn("Create station", { cls: "primary", icon: "plus", onclick: save }))));
}

async function stationDetail(root, id, tab) {
  const reveal = S.revealSecrets ? "?reveal=1" : "";
  const s = await api("GET", `/api/stations/${encodeURIComponent(id)}${reveal}`);
  setCrumbs({ label: "Stations", href: "#/stations" }, s.label || id);
  const tabs = [["service", "Service", "radio"], ["audio", "Subchannel", "layers"]];
  if (s.kind === "audio") tabs.push(["encoder", "Encoder & feed", "volume"]);
  if (s.encoder && s.pad_program) tabs.push(["pad", "DLS & slides", "image"]);
  tabs.push(["components", "Components", "braces"]);
  if (s.issues.length) tabs.push(["issues", `Issues (${s.issues.length})`, "alert"]);
  const tabBar = h("div", { class: "tabs" }, tabs.map(([k, l, ic]) => h("button", { class: k === tab ? "on" : "", onclick: () => { location.hash = `#/stations/${encodeURIComponent(id)}/${k}`; } }, icon(ic), l)));
  const body = h("div");
  const ro = !isEditor();
  const save = async (payload) => {
    try { const r = await api("PUT", `/api/stations/${encodeURIComponent(id)}`, payload); toast("Saved to the draft. Apply when ready.", "ok"); pokeStatus();
      const next = `#/stations/${encodeURIComponent(r.id)}/${tab}`;
      if (location.hash === next) route(); else location.hash = next;   // hashchange re-renders by itself
    } catch (e) { /* toasted */ }
  };
  const svc = s.service || {};
  const sc = s.subchannel || {};
  const footer = (fn) => ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save", { cls: "primary", onclick: fn }));

  if (tab === "service") {
    const label = inp(svc.label, { maxlength: 16, disabled: ro }), short = inp(svc.shortlabel, { maxlength: 8, disabled: ro }), sid = inp(svc.id, { class: "mono", disabled: ro }), ecc = inp(svc.ecc, { class: "mono", disabled: ro });
    const pty = sel(svc.pty || 0, PTY.map((p, i) => [i, `${i} ${p}`]), { disabled: ro }), ptysd = sel(svc["pty-sd"] || "static", [["static", "static"], ["dynamic", "dynamic"]], { disabled: ro });
    const langv = svc.language || "";
    const lang = sel(langv, LANGS.some((l) => l[0].toLowerCase() === langv.toLowerCase()) ? LANGS.map((l) => [l[0].toLowerCase() === langv.toLowerCase() ? langv : l[0], l[1]]) : [[langv, langv], ...LANGS], { disabled: ro });
    const ann = svc.announcements || {};
    const annBoxes = ANN.map((a) => toggle(a, String(ann[a]) === "true", { disabled: ro }));
    const clusters = inp(ann.clusters || "", { placeholder: "1,2", disabled: ro });
    put(body, h("div", { class: "card card-pad stack" },
      h("div", { class: "grid-4" }, field("Label", label, { max: 16 }), field("Short label", short, { max: 8 }), field("SId", sid), field("ECC", ecc, { hint: "Empty = ensemble ECC." })),
      h("div", { class: "grid-3" }, field("Programme type", pty), field("PTY static/dynamic", ptysd), field("Language", lang)),
      h("h3", null, "Announcement support"), h("p", { class: "small muted" }, "Which announcement types this service takes part in (FIG 0/18), and in which clusters. Clusters are defined under Announcements."),
      h("div", { class: "check-grid" }, annBoxes.map((b) => b.el)), field("Clusters", clusters, { hint: "Comma separated cluster ids." }),
      footer(() => save({ service: { label: label.value, shortlabel: short.value, id: sid.value, ecc: ecc.value, pty: pty.value, "pty-sd": ptysd.value, language: lang.value,
        announcements: { types: ANN.filter((a, i) => annBoxes[i].box.checked), clusters: clusters.value } } }))));
  }
  if (tab === "audio") {
    const type = sc.type;
    const bitrate = inp(sc.bitrate, { type: "number", min: 8, max: 384, step: 8, disabled: ro });
    const prot = protectionPicker(type, () => bitrate.value, sc["protection-profile"], sc.protection);
    bitrate.addEventListener("input", () => prot.calc());
    const scid = inp(sc.id, { type: "number", min: 0, max: 63, disabled: ro });
    const proto = sel(sc.inputproto || "edi", [["edi", "EDI"], ["zmq", "ZMQ"], ["file", "file"], ["fifo", "fifo"], ["udp", "UDP"], ["stp", "STP"]], { disabled: ro });
    const uri = inp(sc.inputuri, { class: "mono", disabled: ro });
    const bm = sel(sc["buffer-management"] || "prebuffering", [["prebuffering", "prebuffering"], ["timestamped", "timestamped"]], { disabled: ro });
    const buf = inp(sc.buffer || "", { type: "number", disabled: ro }), pre = inp(sc.prebuffering || "", { type: "number", disabled: ro });
    if (ro) { prot.prof.disabled = true; prot.lvl.disabled = true; }
    put(body, h("div", { class: "card card-pad stack" },
      h("div", { class: "grid-3" }, field("Type", h("input", { type: "text", value: `${type} (${type === "audio" ? "MP2" : type === "dabplus" ? "DAB+" : type})`, disabled: true }), { hint: "Change the codec under Encoder & feed." }),
        field("Bitrate (kbps)", bitrate), field("Subchannel id", scid)),
      prot.el,
      h("h3", null, "Input"), h("div", { class: "grid-2" }, field("Protocol", proto), field("URI", uri, { hint: "tcp://0.0.0.0:PORT for EDI, a file path for packet data." })),
      h("div", { class: "grid-3" }, field("Buffer management", bm), field("Buffer (frames)", buf), field("Prebuffering (frames)", pre)),
      footer(() => save({ subchannel: { bitrate: bitrate.value, "protection-profile": prot.prof.value, protection: prot.lvl.value, id: scid.value, inputproto: proto.value, inputuri: uri.value,
        "buffer-management": bm.value, buffer: buf.value, prebuffering: pre.value } }))));
  }
  if (tab === "encoder") encoderTab(body, s, save, ro);
  if (tab === "pad") padTab(body, s, save, ro);
  if (tab === "components") componentsTab(body, s, ro);
  if (tab === "issues") put(body, issueList(s.issues));

  const actions = h("div", { class: "row" });
  if (isEditor()) {
    actions.appendChild(btn("Remove station", { cls: "danger ghost", icon: "trash", onclick: async () => {
      location.hash = "#/stations";
      toast("Mark it for removal with the bin icon, then Preview changes to see what gets renumbered.");
    } }));
  }
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, s.label || id),
    h("p", null, [codecBadge(s.codec), ` ${s.bitrate} kbps · ${s.protection} · ${s.cu} CU · `, s.feed === "local" ? `fed by ${s.audio_program}` : s.feed === "external" ? `external feed on port ${s.port}` : s.feed, s.ptag ? ` · ${s.ptag}` : ""])),
    h("span", { class: "spacer" }), actions), tabBar, body);
}

function issueList(issues) {
  if (!issues.length) return h("div", { class: "banner green" }, icon("check"), "No issues found.");
  return h("div", { class: "stack tight" }, issues.map((i) => h("div", { class: "banner " + (i.severity === "error" ? "red" : i.severity === "warning" ? "amber" : "blue") },
    icon(i.severity === "info" ? "info" : "alert"), h("div", { class: "grow" }, i.message),
    i.fix && isEditor() ? btn("Fix", { cls: "sm", onclick: async () => { await api("POST", "/api/checks/fix", { fix: i.fix }); toast("Fixed in the draft.", "ok"); pokeStatus(); route(); } }) : null)));
}

function encoderTab(body, s, save, ro) {
  const enc = s.encoder;
  if (s.feed !== "local") {
    const ikind = sel((S.caps && S.caps.inputs && S.caps.inputs[0]) || "gstreamer", inputOptions());
    const iurl = inp("", { placeholder: "https://stream.example/live" });
    put(body, h("div", { class: "card card-pad stack" },
      h("div", { class: "banner blue" }, icon("globe"), h("div", { class: "grow" }, h("b", null, "Fed externally. "),
        `odr-dabmux listens on ${s.inputproto || "?"} ${s.inputuri || ""}; another machine sends the audio here. No local encoders are created for it.`)),
      s.parked ? h("p", { class: "small" }, "This station had local encoders before. Switching back restores them exactly as they were.") : null,
      !ro ? h("div", { class: "stack" }, h("h3", null, "Switch to a local encoder"),
        s.parked ? null : h("div", { class: "grid-2" }, field("Input", ikind), field("Source", iurl)),
        h("div", { class: "row" }, h("span", { class: "spacer" }), btn(s.parked ? "Restore local encoders" : "Create local encoders", { cls: "primary", icon: "shuffle", onclick: async () => {
          try {
            await api("POST", `/api/stations/${encodeURIComponent(s.id)}/feed`, { feed: "local", opts: s.parked ? {} : { encoder: { input_kind: ikind.value, input: iurl.value } } });
            toast("Staged. Apply to start the encoders.", "ok"); pokeStatus(); route();
          } catch (e) { /* toasted */ }
        } }))) : null));
    return;
  }
  const kind = sel(enc.input_kind || "gstreamer", inputOptions(), { disabled: ro });
  const input = inp(enc.input, { class: "mono", disabled: ro });
  const codec = sel(enc.codec_auto ? "auto" : enc.codec, codecOptions(), { disabled: ro });
  const rate = sel(enc.rate || 48000, [[48000, "48 kHz"], [32000, "32 kHz (DAB+)"], [24000, "24 kHz (MP2 LSF)"]], { disabled: ro });
  const channels = sel(enc.channels || 2, [[2, "Stereo"], [1, "Mono"]], { disabled: ro });
  const dabmode = sel(enc.dabmode || "", [["", "Default (joint stereo / mono)"], ["s", "Stereo"], ["j", "Joint stereo"], ["d", "Dual mono"], ["m", "Mono"]], { disabled: ro });
  const dabpsy = sel(enc.dabpsy == null ? 1 : enc.dabpsy, [[0, "0"], [1, "1 (encoder default)"], [2, "2"], [3, "3"]], { disabled: ro });
  const pad = inp(enc.pad ?? "", { type: "number", min: 0, max: 196, disabled: ro });
  const silence = inp(enc.silence ?? "", { type: "number", min: 0, disabled: ro });
  const drift = toggle("Drift compensation (--drift-comp)", enc.drift_comp, { disabled: ro });
  const ab = toggle("Afterburner (DAB+ quality, more CPU)", enc.afterburner, { disabled: ro });
  const gain = inp(enc.audio_gain ?? "", { placeholder: "dB", disabled: ro });
  const bw = inp(enc.bandwidth ?? "", { type: "number", placeholder: "Hz", disabled: ro });
  const icy = inp(enc.icy_text || "", { class: "mono", disabled: ro });
  const icydl = toggle("Write DL Plus tags with the ICY text", enc.icy_dlplus, { disabled: ro });
  const cache = inp(enc.vlc_cache || "", { type: "number", placeholder: "ms", disabled: ro });
  const remote = enc.outputs.filter((o) => !o.local);
  const remoteRows = h("div", { class: "stack tight" });
  const remoteList = remote.map((o) => ({ kind: o.kind, uri: o.uri }));
  const drawRemote = () => {
    clear(remoteRows);
    remoteList.forEach((o, i) => remoteRows.appendChild(h("div", { class: "row" },
      sel(o.kind, [["zmq", "ZMQ (-o)"], ["edi", "EDI (-e)"]], { disabled: ro, onchange: (e) => { o.kind = e.target.value; } }),
      inp(o.uri, { class: "mono grow", disabled: ro, oninput: (e) => { o.uri = e.target.value; } }),
      ro ? null : iconBtn("trash", "Remove", () => { remoteList.splice(i, 1); drawRemote(); }))));
    if (!ro) remoteRows.appendChild(btn("Add output to another mux", { cls: "sm ghost", icon: "plus", onclick: () => { remoteList.push({ kind: "zmq", uri: "tcp://" }); drawRemote(); } }));
  };
  drawRemote();
  const mp2Box = h("div", { class: "grid-2" }, field("MP2 psychoacoustic model (--dabpsy)", dabpsy, { hint: "0-3. Higher models analyse more; 1 is the encoder default." }), field("MP2 channel mode (--dabmode)", dabmode));
  const aacBox = h("div", { class: "stack" }, ab.el, field("Bandwidth (-B)", bw, { hint: "Optional AAC low-pass in Hz." }));
  const vlcBox = field("VLC network cache (ms)", cache);
  const sync = () => { mp2Box.classList.toggle("hidden", codec.value !== "mp2"); aacBox.classList.toggle("hidden", codec.value === "mp2"); vlcBox.classList.toggle("hidden", kind.value !== "vlc"); };
  [codec, kind].forEach((x) => x.addEventListener("change", sync));
  sync();
  const revealBtn = isAdmin() && enc.input_has_secret ? btn(S.revealSecrets ? "Hide key" : "Show key", { cls: "sm ghost", icon: "eye", onclick: () => { S.revealSecrets = !S.revealSecrets; route(); } }) : null;
  put(body, h("div", { class: "card card-pad stack" },
    h("div", { class: "row" }, h("span", { class: "chip green" }, "Local encoder"), h("span", { class: "mono small muted" }, `${s.audio_program}${s.pad_program ? " + " + s.pad_program : ""}`), h("span", { class: "spacer" }),
      ro ? null : btn("Switch to external feed", { cls: "ghost", icon: "shuffle", onclick: async () => {
        const ok = await confirmDialog(`The encoder programs for ${s.label} will be removed from supervisor on Apply (they're kept, so switching back restores them). odr-dabmux keeps listening on port ${s.port}: point the remote encoder there.`, { okText: "Switch to external" });
        if (!ok) return;
        try { await api("POST", `/api/stations/${encodeURIComponent(s.id)}/feed`, { feed: "external", opts: {} }); toast("Staged.", "ok"); pokeStatus(); route(); } catch (e) { /* toasted */ }
      } })),
    h("h3", null, "Source"),
    h("div", { class: "grid-2" }, field("Input", kind, { hint: S.caps && S.caps.audioenc ? `This odr-audioenc supports: ${S.caps.inputs.join(", ")}` : "" }),
      field("Source", h("div", { class: "row" }, input, revealBtn), { hint: enc.input_has_secret ? "Contains a key/token: shown masked (•••). Leave it as is to keep the key." : "" })),
    vlcBox,
    h("h3", null, "Codec"),
    h("div", { class: "grid-3" }, field("Codec", codec, { hint: enc.codec_auto ? `odr-audioenc picks ${CODEC_LONG[enc.codec]} at this bitrate.` : "" }), field("Sample rate", rate), field("Channels", channels)),
    mp2Box, aacBox,
    h("h3", null, "Behaviour"),
    h("div", { class: "grid-3" }, field("PAD length (bytes)", pad, { hint: "6, or 8-196. 0 = no DLS/slides." }), field("Silence timeout (s)", silence, { hint: "Restart after this much silence." }), field("Audio gain (dB)", gain)),
    drift.el,
    h("div", { class: "grid-2" }, field("Write ICY text to", icy, { hint: "Lets the stream's now-playing feed DLS." }), h("div", { class: "field" }, h("label", null, " "), icydl.el)),
    h("h3", null, "Also send to"), h("p", { class: "small muted" }, `The local output to odr-dabmux (port ${s.port}) is managed for you.`), remoteRows,
    footer2(ro, () => save({ encoder: {
      input_kind: kind.value, input: input.value, codec: codec.value, rate: parseInt(rate.value), channels: parseInt(channels.value),
      dabmode: codec.value === "mp2" ? dabmode.value : "", dabpsy: codec.value === "mp2" ? dabpsy.value : "",
      pad: pad.value, silence: silence.value, drift_comp: drift.box.checked, afterburner: ab.box.checked, audio_gain: gain.value, bandwidth: codec.value === "mp2" ? "" : bw.value,
      icy_text: icy.value, icy_dlplus: icydl.box.checked, vlc_cache: kind.value === "vlc" ? cache.value : "", remote_outputs: remoteList.filter((o) => o.uri && o.uri !== "tcp://") } }))));
}
function footer2(ro, fn) { return ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save", { cls: "primary", onclick: fn })); }

function padTab(body, s, save, ro) {
  const e = s.encoder;
  const dir = inp(e.slide_dir || "", { class: "mono", disabled: ro });
  const sleep = inp(e.sleep ?? "", { type: "number", min: 1, disabled: ro });
  const dls = h("textarea", { rows: 3, class: "mono", disabled: ro }); dls.value = (e.dls_files || []).join("\n");
  const label = inp(e.label ?? "", { type: "number", disabled: ro }), labelIns = inp(e.label_ins ?? "", { type: "number", disabled: ro });
  const raw = toggle("Send slides as they are (--raw-slides, no recompression)", e.raw_slides, { disabled: ro });
  const erase = toggle("Delete slides after sending them once (--erase)", e.erase, { disabled: ro });
  const charset = sel(e.charset ?? "", [["", "UTF-8 / default"], ["0", "Complete EBU Latin (0)"], ["15", "UTF-8 (15)"]], { disabled: ro });
  put(body, h("div", { class: "card card-pad stack" },
    h("div", { class: "grid-2" }, field("Slide folder (--dir)", dir), field("Seconds per slide (--sleep)", sleep)),
    field("DLS text file(s) (--dls)", dls, { hint: "One per line. Several files rotate." }),
    h("div", { class: "grid-3" }, field("DL Plus label (--label)", label), field("Label insertion (--label-ins)", labelIns, { hint: "ms" }), field("Charset", charset)),
    raw.el, erase.el,
    h("p", { class: "small muted" }, "Anything that writes DLS text or slides for this station (now-playing scripts, slide updaters) writes into these paths. If the station is renumbered, they move with it and the impact report tells you."),
    footer2(ro, () => save({ pad: { slide_dir: dir.value, sleep: sleep.value, dls_files: dls.value.split("\n").map((x) => x.trim()).filter(Boolean), label: label.value, label_ins: labelIns.value,
      raw_slides: raw.box.checked, erase: erase.box.checked, charset: charset.value } }))));
}

function userAppPicker(current, ro) {
  const apps = [["slideshow", "Slideshow"], ["spi", "SPI / EPG"], ["journaline", "Journaline"], ["website", "Website (packet only)"]];
  const cur = Array.isArray(current) ? current : current ? [current] : [];
  const boxes = apps.map(([k, l]) => [k, toggle(l, cur.includes(k), { disabled: ro })]);
  return { el: h("div", { class: "check-grid" }, boxes.map((b) => b[1].el)), value: () => boxes.filter((b) => b[1].box.checked).map((b) => b[0]) };
}

function componentsTab(body, s, ro) {
  const comp = s.component || {};
  const ua = userAppPicker((comp["user-applications"] || {}).userapp, ro);
  const secondary = s.secondary_components || [];
  const svcSel = sel("", [["", "Choose a service"], ...s.services.filter((x) => x.uid !== s.service_uid).map((x) => [x.uid, `${x.label} (${x.uid})`])]);
  const secLabel = inp("", { maxlength: 16, placeholder: "Label shown for this component" });
  put(body, h("div", { class: "stack" },
    h("div", { class: "card card-pad stack" }, h("h3", null, `Primary component ${s.component_uid || ""}`),
      h("p", { class: "small muted" }, "User applications signalled in FIG 0/13 for the PAD of this service."), ua.el,
      ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save", { cls: "primary", onclick: async () => {
        try { await api("PUT", `/api/components/${encodeURIComponent(s.component_uid)}`, { user_apps: ua.value() }); toast("Saved.", "ok"); pokeStatus(); } catch (e) { /* toasted */ }
      } }))),
    h("div", { class: "card card-pad stack" }, h("h3", null, "Secondary components"),
      h("p", { class: "small muted" }, "Show this station's audio as an extra component of another service (like a '90s' sub-channel under the main brand)."),
      secondary.length ? h("table", null, h("tbody", null, secondary.map((c) => h("tr", null, h("td", { class: "mono" }, c.uid), h("td", null, c.label || ""), h("td", null, `under ${c.service}`),
        ro ? null : h("td", null, iconBtn("trash", "Remove", async () => { if (await confirmDialog(`Remove component ${c.uid}?`, { danger: true, okText: "Remove" })) { await api("DELETE", `/api/components/${encodeURIComponent(c.uid)}`); pokeStatus(); route(); } })))))) : h("p", { class: "muted small" }, "None."),
      ro ? null : h("div", { class: "grid-3" }, field("Under service", svcSel), field("Label", secLabel, { max: 16 }), h("div", { class: "field" }, h("label", null, " "),
        btn("Add", { icon: "plus", onclick: async () => {
          if (!svcSel.value) return toast("Choose a service.", "error");
          try { await api("POST", `/api/stations/${encodeURIComponent(s.id)}/components`, { service: svcSel.value, label: secLabel.value }); toast("Added.", "ok"); pokeStatus(); route(); } catch (e) { /* toasted */ }
        } })))),
    h("p", { class: "small muted" }, "Linkage (FM/DAB alternatives) for this service is edited under ", h("a", { href: "#/linking" }, "Linking & FI"), ".")));
}

/* ============================== ensemble ============================== */

async function pageEnsemble(root) {
  setCrumbs("Ensemble");
  const e = await api("GET", "/api/ensemble");
  const ro = !isEditor();
  const f = (k, attrs = {}) => inp(e[k] ?? "", { disabled: ro, ...attrs });
  const id = f("id", { class: "mono" }), ecc = f("ecc", { class: "mono" }), label = f("label", { maxlength: 16 }), short = f("shortlabel", { maxlength: 8 });
  const lto = f("local-time-offset", { placeholder: "auto" });
  const intl = sel(e["international-table"] || 1, [[1, "1 - RDS PTY (Europe)"], [2, "2 - RBDS PTY (North America)"]], { disabled: ro });
  const rc = sel(e["reconfig-counter"] || "", [["", "not sent"], ["hash", "hash (changes with the config)"]], { disabled: ro });
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Ensemble"), h("p", null, "The multiplex itself."))),
    h("div", { class: "card card-pad stack" },
      h("div", { class: "grid-4" }, field("Ensemble id (EId)", id), field("ECC", ecc), field("Label", label, { max: 16 }), field("Short label", short, { max: 8 })),
      h("div", { class: "grid-3" }, field("Local time offset", lto, { hint: "auto, or hours like 1 / 2." }), field("International table", intl), field("Reconfiguration counter", rc)),
      ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save", { cls: "primary", onclick: async () => {
        try { await api("PUT", "/api/ensemble", { id: id.value, ecc: ecc.value, label: label.value, shortlabel: short.value, "local-time-offset": lto.value, "international-table": intl.value, "reconfig-counter": rc.value }); toast("Saved to the draft.", "ok"); pokeStatus(); } catch (x) { /* toasted */ }
      } }))));
}

/* ============================== generic named-block editor ============================== */

function blockList({ title, items, render, add, ro, empty }) {
  const wrap = h("div", { class: "stack" });
  const draw = () => {
    clear(wrap);
    const keys = Object.keys(items);
    if (!keys.length) wrap.appendChild(h("p", { class: "muted" }, empty || "None yet."));
    for (const k of keys) {
      const card = h("div", { class: "card card-pad stack" },
        h("div", { class: "row" }, h("b", { class: "mono" }, k), h("span", { class: "spacer" }), ro ? null : iconBtn("trash", "Remove", () => { delete items[k]; draw(); })),
        render(k, items[k], draw));
      wrap.appendChild(card);
    }
    if (!ro) wrap.appendChild(h("div", { class: "row" }, btn(title, { icon: "plus", onclick: () => { const k = prompt("Name (letters, digits, -)"); if (!k || !/^[A-Za-z0-9_-]+$/.test(k)) return; if (items[k]) return toast("That name exists.", "error"); items[k] = add(); draw(); } })));
  };
  draw();
  return wrap;
}
const bind = (obj, key, el, map = (v) => v) => { el.addEventListener("input", () => { obj[key] = map(el.type === "checkbox" ? el.checked : el.value); }); el.addEventListener("change", () => { obj[key] = map(el.type === "checkbox" ? el.checked : el.value); }); return el; };
const tf = (v) => String(v) === "true";

async function saveSection(name, data) {
  try { await api("PUT", `/api/section/${name}`, data); toast("Saved to the draft. Apply when ready.", "ok"); pokeStatus(); } catch (e) { /* toasted */ }
}

/* ============================== linking & FI ============================== */

async function pageLinking(root) {
  setCrumbs("Linking & FI");
  const [linking, fi, oth, st] = await Promise.all([api("GET", "/api/section/linking"), api("GET", "/api/section/frequency_information"),
    api("GET", "/api/section/other-services"), api("GET", "/api/stations")]);
  const ro = !isEditor();
  const svcOpts = st.stations.filter((s) => s.service_uid).map((s) => [s.service_uid, `${s.label} (${s.service_uid})`]);
  const linkEditor = blockList({ title: "Add linkage set", items: linking, ro, empty: "No service linking.",
    add: () => ({ lsn: "0x001", active: "true", hard: "true", international: "false", keyservice: svcOpts[0] ? svcOpts[0][0] : "", list: {} }),
    render: (k, ls) => {
      ls.list = ls.list || {};
      const flags = [["active", "Active"], ["hard", "Hard link (same programme)"], ["international", "International (other ECC)"]].map(([f, l]) => { const t = toggle(l, tf(ls[f]), { disabled: ro }); bind(ls, f, t.box, (v) => v ? "true" : "false"); return t.el; });
      const list = blockList({ title: "Add linked service", items: ls.list, ro, empty: "No linked services yet.",
        add: () => ({ type: "fm" }),
        render: (kk, it) => h("div", { class: "grid-3" },
          field("Type", bind(it, "type", sel(it.type, [["fm", "FM (RDS PI)"], ["dab", "DAB (SId)"], ["drm", "DRM"], ["amss", "AMSS"]], { disabled: ro }))),
          field(it.type === "fm" ? "PI code" : "Id", bind(it, "id", inp(it.id, { class: "mono", disabled: ro }))),
          field("ECC", bind(it, "ecc", inp(it.ecc || "", { class: "mono", disabled: ro, placeholder: "same as ensemble" })))) });
      return h("div", { class: "stack" }, h("div", { class: "grid-2" }, field("Linkage set number (LSN)", bind(ls, "lsn", inp(ls.lsn, { class: "mono", disabled: ro })), { hint: "12-bit, unique in the country." }),
        field("Key service", bind(ls, "keyservice", sel(ls.keyservice, svcOpts, { disabled: ro })))), h("div", { class: "row wrap" }, flags), list);
    } });
  const fiEditor = blockList({ title: "Add frequency list", items: fi, ro, empty: "No frequency information.",
    add: () => ({ range_modulation: "fm", continuity: "true" }),
    render: (k, f, redraw) => {
      const mod = bind(f, "range_modulation", sel(f.range_modulation, [["fm", "FM"], ["dab", "DAB"], ["drm", "DRM"], ["amss", "AMSS"]], { disabled: ro }));
      mod.addEventListener("change", () => { if (f.range_modulation === "dab") { delete f.pi_code;  f.frequencies = typeof f.frequencies === "object" ? f.frequencies : {}; } else { delete f.eid; f.frequencies = typeof f.frequencies === "string" ? f.frequencies : ""; } redraw(); });
      const cont = toggle("Continuity (same programme, seamless)", tf(f.continuity), { disabled: ro }); bind(f, "continuity", cont.box, (v) => v ? "true" : "false");
      let freqs;
      if (f.range_modulation === "dab") {
        f.frequencies = typeof f.frequencies === "object" ? f.frequencies : {};
        freqs = blockList({ title: "Add DAB channel", items: f.frequencies, ro, add: () => ({ frequency: "174.928", signal_mode_1: "true", adjacent: "true" }),
          render: (kk, c) => {
            const ch = sel(String(c.frequency), [...DAB_CHANNELS.map(([n, mhz]) => [String(mhz), `${n} - ${mhz} MHz`])], { disabled: ro });
            bind(c, "frequency", ch);
            const sm = toggle("Mode I", tf(c.signal_mode_1), { disabled: ro }); bind(c, "signal_mode_1", sm.box, (v) => v ? "true" : "false");
            const adj = toggle("Adjacent area", tf(c.adjacent), { disabled: ro }); bind(c, "adjacent", adj.box, (v) => v ? "true" : "false");
            return h("div", { class: "row wrap" }, field("Channel", ch), sm.el, adj.el);
          } });
      } else freqs = field("Frequencies (MHz / kHz, space separated)", bind(f, "frequencies", inp(f.frequencies || "", { class: "mono", disabled: ro })));
      return h("div", { class: "stack" }, h("div", { class: "grid-3" }, field("Range / modulation", mod),
        f.range_modulation === "dab" ? field("EId", bind(f, "eid", inp(f.eid || "", { class: "mono", disabled: ro }))) : field(f.range_modulation === "fm" ? "PI code" : "Id", bind(f, "pi_code", inp(f.pi_code || "", { class: "mono", disabled: ro }))),
        h("div", { class: "field" }, h("label", null, " "), cont.el)), freqs);
    } });
  const othEditor = blockList({ title: "Add other-ensemble service", items: oth, ro, empty: "No services announced in other ensembles (FIG 0/24).",
    add: () => ({}),
    render: (k, o) => h("div", { class: "grid-2" }, field("SId", bind(o, "id", inp(o.id, { class: "mono", disabled: ro }))),
      field("Other ensembles (EIds, comma separated)", bind(o, "other_ensembles", inp(o.other_ensembles || "", { class: "mono", disabled: ro })))) });
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Linking & frequency information"), h("p", null, "Tell receivers where else each service can be heard (FM, other DAB muxes)."))),
    h("h2", null, "Service linking (FIG 0/6)"), linkEditor,
    ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save linking", { cls: "primary", onclick: () => saveSection("linking", linking) })),
    h("div", { class: "section-gap" }), h("h2", null, "Frequency information (FIG 0/21)"), fiEditor,
    ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save frequency information", { cls: "primary", onclick: () => saveSection("frequency_information", fi) })),
    h("div", { class: "section-gap" }), h("h2", null, "Services in other ensembles (FIG 0/24)"), othEditor,
    ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save other ensembles", { cls: "primary", onclick: () => saveSection("other-services", oth) })));
}

/* ============================== announcements ============================== */

async function pageAnnouncements(root) {
  setCrumbs("Announcements");
  const [cl, st] = await Promise.all([api("GET", "/api/section/ensemble.announcements"), api("GET", "/api/stations")]);
  const ro = !isEditor();
  const subOpts = st.stations.filter((s) => s.kind === "audio").map((s) => [s.subchannel_uid, `${s.label} (${s.subchannel_uid})`]);
  const ed = blockList({ title: "Add announcement cluster", items: cl, ro, empty: "No announcement clusters.",
    add: () => ({ cluster: "1", flags: { Traffic: "true" }, subchannel: subOpts[0] ? subOpts[0][0] : "" }),
    render: (k, c) => {
      c.flags = c.flags || {};
      const boxes = ANN.map((a) => { const t = toggle(a, tf(c.flags[a]), { disabled: ro }); t.box.addEventListener("change", () => { if (t.box.checked) c.flags[a] = "true"; else delete c.flags[a]; }); return t.el; });
      return h("div", { class: "stack" }, h("div", { class: "grid-2" }, field("Cluster id", bind(c, "cluster", inp(c.cluster, { type: "number", min: 1, max: 254, disabled: ro }))),
        field("Announcement audio comes from", bind(c, "subchannel", sel(c.subchannel, subOpts, { disabled: ro })))),
        h("div", { class: "check-grid" }, boxes),
        h("p", { class: "small muted" }, "Start/stop an announcement live through odr-dabmux remote control (set <name> active 1). Which services follow it is set per service (Service tab → Announcement support)."));
    } });
  const using = st.stations.filter((s) => s.service && s.service.announcements);
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Announcements"), h("p", null, "Traffic, news, alarm… switching (FIG 0/19)."))),
    ed, ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save clusters", { cls: "primary", onclick: () => saveSection("ensemble.announcements", cl) })),
    h("div", { class: "section-gap" }), h("h2", null, "Services taking part"),
    using.length ? h("div", { class: "card" }, h("table", null, h("tbody", null, using.map((s) => h("tr", { class: "click", onclick: () => { location.hash = `#/stations/${s.id}/service`; } },
      h("td", null, s.label), h("td", { class: "small" }, ANN.filter((a) => tf(s.service.announcements[a])).join(", ") || "—"), h("td", { class: "mono small" }, s.service.announcements.clusters || "")))))) :
      h("p", { class: "muted" }, "No service has announcement support switched on yet."));
}

/* ============================== data services ============================== */

const DATA_PRESETS = [["spi", "SPI / EPG"], ["journaline", "Journaline"], ["tpeg", "TPEG"], ["website", "Broadcast Website"], ["slideshow", "Slideshow (packet)"], ["custom", "Custom"]];
const DATA_HINTS = {
  spi: "Service & Programme Information from ODR-SPI-Generator. Use the same bitrate and packet address you set in the generator.",
  journaline: "Journaline text news (ETSI TS 102 979). Point it at the .dat file your Journaline generator writes.",
  tpeg: "TPEG traffic info over TDC. odr-dabmux has no userapp name for TPEG, so the older figtype 0x4 setting is used.",
  website: "MOT Broadcast Website (packet mode only).", slideshow: "MOT slideshow as its own packet-mode service.", custom: "Set DSCTy, user application and data groups yourself.",
};

async function pageData(root) {
  setCrumbs("Data services");
  const st = await api("GET", "/api/stations");
  const data = st.stations.filter((s) => s.kind === "data");
  const ro = !isEditor();
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Data services"), h("p", null, "Packet-mode services that read a .dat file from a generator: SPI, Journaline, TPEG…")),
    h("span", { class: "spacer" }), ro ? null : btn("Add data service", { cls: "primary", icon: "plus", onclick: () => dataEditor(null) })),
    data.length ? h("div", { class: "station-grid" }, data.map((s) => {
      const c = s.component || {};
      const ua = (c["user-applications"] || {}).userapp;
      return h("button", { class: "station-card", type: "button", onclick: () => dataEditor(s) },
        h("div", { class: "sc-head" }, h("div", { class: "logo-tile" }, icon("database")), h("div", { class: "titles" }, h("h3", { class: "ellipsis" }, s.label), h("div", { class: "sub" }, `${s.type} · ${s.bitrate} kbps · ${s.protection} · ${s.cu} CU`))),
        h("div", { class: "sc-inset" }, h("div", { class: "desc mono ellipsis" }, s.inputuri || "no file")),
        h("div", { class: "sc-foot" }, h("span", { class: "chip" }, `SId ${s.id}`), h("span", { class: "chip" }, `address ${c.address || "?"}`),
          ua ? h("span", { class: "chip accent" }, [].concat(ua).join(", ")) : c.figtype ? h("span", { class: "chip accent" }, `figtype ${c.figtype}`) : null,
          String(c.datagroup) === "true" ? h("span", { class: "chip" }, "data groups") : null,
          (s.secondary_components || []).length ? h("span", { class: "chip blue" }, `under ${(s.secondary_components || []).length} station${(s.secondary_components || []).length === 1 ? "" : "s"}`) : null));
    })) : h("div", { class: "empty" }, h("h3", null, "No data services"), h("p", null, "Add SPI, Journaline or TPEG and point it at the generator's .dat file.")));
}

async function dataEditor(s) {
  const ro = !isEditor();
  let attached = [];
  try {
    if (s) attached = (await api("GET", `/api/data-services/${encodeURIComponent(s.id)}/attached`)).attached;
  } catch (e) { /* toasted */ }
  // odr-dabmux can't share one component between services, so copies under stations stay empty on
  // receivers: data services are standalone only. Saving removes any copies made earlier.
  const attachField = attached.length ? h("div", { class: "banner amber" }, icon("alert"), h("div", { class: "grow" },
    `This service is also listed under ${attached.length} station${attached.length === 1 ? "" : "s"}. Receivers leave those copies empty, so Save removes them and keeps it as a standalone service.`)) : null;
  const attachedValue = () => [];
  const datOut = h("div");   // .dat check results; must exist before `body` below uses it
  const c = (s && s.component) || {};
  const sc = (s && s.subchannel) || {};
  const svc = (s && s.service) || {};
  const ua = [].concat((c["user-applications"] || {}).userapp || []);
  const guess = ua.includes("spi") ? "spi" : ua.includes("journaline") ? "journaline" : String(c.figtype || "").toLowerCase() === "0x4" ? "tpeg" : ua.includes("website") ? "website" : ua.includes("slideshow") ? "slideshow" : (s ? "custom" : "spi");
  const preset = sel(guess, DATA_PRESETS, { disabled: ro || !!s });
  const hint = h("div", { class: "banner blue" });
  const label = inp(svc.label || "", { maxlength: 16, disabled: ro }), short = inp(svc.shortlabel || "", { maxlength: 8, disabled: ro });
  const sid = inp(svc.id || "", { class: "mono", placeholder: "0xE3222345", disabled: ro });
  const file = inp(sc.inputuri || "", { class: "mono", placeholder: "/home/ryan/dab/journaline/output.dat", disabled: ro });
  const bitrate = inp(sc.bitrate || 16, { type: "number", min: 8, step: 8, disabled: ro });
  const subtype = sel(sc.type || "packet", [["packet", "packet"], ["enhancedpacket", "enhancedpacket (adds RS FEC)"]], { disabled: ro });
  const prot = protectionPicker("packet", () => bitrate.value, sc["protection-profile"] || "EEP_A", sc.protection || 3);
  if (ro) { prot.prof.disabled = true; prot.lvl.disabled = true; }
  bitrate.addEventListener("input", () => prot.calc());
  const addr = inp(c.address || "0x1", { class: "mono", disabled: ro });
  const dscty = inp(c.type ?? "", { type: "number", disabled: ro });
  const dg = toggle("Use MSC data groups", s ? String(c.datagroup) === "true" : true, { disabled: ro });
  const uap = userAppPicker(ua, ro);
  const fig = inp(c.figtype || "", { class: "mono", placeholder: "0x4 for TPEG", disabled: ro });
  const pick = btn("Browse", { cls: "ghost", icon: "folder", onclick: async () => { const f = await fileBrowser({ title: "Choose the .dat file", mode: "file", exts: "dat,eti,bin", start: file.value || "/" }); if (f) file.value = f; } });
  const syncHint = () => { clear(hint).append(icon("info"), h("div", { class: "grow" }, DATA_HINTS[preset.value])); };
  preset.addEventListener("change", syncHint); syncHint();
  const body = h("div", { class: "stack" }, hint, field("Kind", preset),
    h("div", { class: "grid-3" }, field("Label", label, { max: 16 }), field("Short label", short, { max: 8 }), field("Service id", sid, { hint: "8 hex digits for data services." })),
    field(".dat file written by the generator", h("div", { class: "row" }, file, isAdmin() && !ro ? pick : null)),
    h("div", { class: "grid-2" }, field("Bitrate (kbps)", bitrate), field("Subchannel type", subtype)), prot.el,
    h("div", { class: "grid-3" }, field("Packet address", addr, { hint: "Must match the generator." }), field("DSCTy (component type)", dscty, { hint: "60 = MOT, 5 = TDC. Blank = preset." }), h("div", { class: "field" }, h("label", null, " "), dg.el)),
    field("User applications (FIG 0/13)", uap.el), field("figtype (only for apps without a name, e.g. TPEG 0x4)", fig), attachField, datOut);
  const foot = [btn("Close", { onclick: () => m.close() })];
  if (s) foot.unshift(btn("Check the .dat file", { cls: "ghost", icon: "search", onclick: async () => {
    put(clear(datOut), h("div", { class: "banner blue" }, h("span", { class: "spin" }), "Reading the file…"));
    try {
      const r = await api("GET", `/api/data-services/${encodeURIComponent(s.id)}/inspect`);
      put(clear(datOut), h("div", { class: "card card-pad stack tight" },
        h("div", { class: "banner " + (r.ok ? "green" : "amber") }, icon(r.ok ? "check" : "alert"),
          h("div", { class: "grow" }, r.ok ? "The file looks right: packets on the configured address." : r.problems.map((x) => h("div", null, x)))),
        r.exists ? h("dl", { class: "kv" },
          h("dt", null, "Packet addresses in the file"), h("dd", { class: "mono" }, Object.entries(r.addresses || {}).map(([a, n]) => `${a} (${n})`).join(", ") || "none"),
          h("dt", null, "Packets read"), h("dd", null, `${r.packets} (${r.padding} padding, ${r.crc_errors} CRC errors, ${r.data_groups} data groups)`),
          h("dt", null, "Packet sizes"), h("dd", { class: "mono" }, Object.entries(r.packet_sizes || {}).map(([k, n]) => `${k} bytes × ${n}`).join(", ")),
          h("dt", null, "Last written"), h("dd", null, fmtAgo(r.mtime))) : null));
      datOut.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) { clear(datOut); }
  } }));
  if (!ro && s) foot.unshift(btn("Remove", { cls: "danger ghost", icon: "trash", onclick: async () => {
    if (!(await confirmDialog(`Remove ${s.label}? Its subchannel frees ${s.cu} CU.`, { danger: true, okText: "Remove" }))) return;
    await api("DELETE", `/api/stations/${encodeURIComponent(s.id)}`); m.close(); pokeStatus(); route();
  } }));
  if (!ro) foot.push(btn(s ? "Save" : "Add", { cls: "primary", onclick: async () => {
    try {
      if (s) await api("PUT", `/api/data-services/${encodeURIComponent(s.id)}`, { service: { label: label.value, shortlabel: short.value, id: sid.value },
        subchannel: { inputuri: file.value, bitrate: bitrate.value, type: subtype.value, "protection-profile": prot.prof.value, protection: prot.lvl.value },
        component: { address: addr.value, datagroup: dg.box.checked ? "true" : "false", type: dscty.value, user_apps: uap.value(), figtype: uap.value().length ? "" : fig.value },
        attached: attachedValue() });
      else await api("POST", "/api/data-services", { preset: preset.value, label: label.value, shortlabel: short.value, sid: sid.value, inputuri: file.value, bitrate: parseInt(bitrate.value),
        subtype: subtype.value, profile: prot.prof.value, protection: parseInt(prot.lvl.value), address: addr.value, datagroup: dg.box.checked, type: dscty.value === "" ? undefined : parseInt(dscty.value),
        userapps: preset.value === "custom" || uap.value().length ? uap.value() : undefined, figtype: fig.value || undefined,
        attached: attachedValue() });
      toast("Saved to the draft.", "ok"); m.close(); pokeStatus(); route();
    } catch (e) { /* toasted */ }
  } }));
  const m = modal({ title: s ? s.label : "Add data service", body, foot, wide: true });
}

/* ============================== DMB ============================== */

async function pageDmb(root) {
  setCrumbs("DMB");
  const d = await api("GET", "/api/dmb");
  const st = await api("GET", "/api/stations");
  const dmbs = st.stations.filter((s) => s.kind === "dmb");
  const ro = !isEditor();
  const steps = d.instructions || [];
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "DMB radio & TV"), h("p", null, "T-DMB services: H.264 video and AAC audio as MPEG-4 Systems (IOD/OD/BIFS, SL) in MPEG-2 TS, in a stream-mode subchannel. Any ffmpeg input works."))),
    h("div", { class: "card card-pad stack" }, h("h3", null, "What this server can do"),
      h("dl", { class: "kv" }, (d.checks || []).flatMap((c) => [h("dt", null, c.label), h("dd", null, h("span", { class: "chip " + (c.ok ? "green" : c.warn ? "amber" : "red") }, icon(c.ok ? "check" : "alert"), c.detail))])),
      d.ready ? h("div", { class: "banner green" }, icon("check"), "Ready to add DMB services.") : h("div", { class: "banner amber" }, icon("alert"), h("div", { class: "grow" }, "Some parts are missing. Follow the steps below.")),
      h("div", { class: "banner blue" }, icon("info"), h("div", { class: "grow" }, d.note || ""))),
    steps.length ? h("div", { class: "card card-pad stack mt" }, h("h3", null, "How to get DMB working"), steps.map((s, i) => h("div", { class: "stack tight" }, h("b", null, `${i + 1}. ${s.title}`), s.text ? h("p", { class: "small" }, s.text) : null, s.cmd ? codeBlock(s.cmd) : null))) : null,
    h("div", { class: "section-gap" }), h("div", { class: "row" }, h("h2", null, "DMB services"), h("span", { class: "spacer" }), ro ? null : btn("Add DMB service", { cls: "primary", icon: "plus", onclick: () => dmbAdd(d) })),
    dmbs.length ? h("div", { class: "station-grid" }, dmbs.map((s) => h("div", { class: "station-card" }, h("div", { class: "sc-head" }, h("div", { class: "logo-tile" }, icon("tv")), h("div", { class: "titles" }, h("h3", null, s.label), h("div", { class: "sub" }, `${s.bitrate} kbps · ${s.protection} · ${s.cu} CU`))),
      h("div", { class: "sc-foot" }, h("span", { class: "chip" }, s.feed), s.dmb_program ? h("span", { class: "chip mono" }, s.dmb_program) : null,
        ro ? null : btn("Remove", { cls: "sm danger ghost", onclick: async () => { if (await confirmDialog(`Remove ${s.label}?`, { danger: true, okText: "Remove" })) { await api("DELETE", `/api/stations/${encodeURIComponent(s.id)}`); pokeStatus(); route(); } } }))))) :
      h("p", { class: "muted" }, "No DMB services."));
}

function dmbAdd(d) {
  const kind = sel("radio", [["radio", "DMB Radio (audio only)"], ["tv", "DMB TV (video + audio)"]]);
  const label = inp("", { maxlength: 16 }), sid = inp("", { class: "mono", placeholder: "0x24F0" });
  const src = inp("", { placeholder: "https://stream.example/live.m3u8, /dev/video0, a file, testsrc…" });
  const ifmt = inp("", { class: "mono", placeholder: "auto (e.g. v4l2, decklink, alsa, lavfi)" });
  const iopts = inp("", { class: "mono", placeholder: "e.g. -video_size 1280x720 -framerate 25" });
  const fps = sel(15, [[12, "12 fps"], [15, "15 fps"], [24, "24 fps"], [25, "25 fps"], [30, "30 fps"]]);
  const abr = inp("", { type: "number", placeholder: "auto" });
  const bitrate = inp("128", { type: "number", min: 32, step: 8 });
  const vbr = inp("384", { type: "number", placeholder: "video kbps" }), size = sel("320x240", [["320x240", "QVGA 320×240"], ["352x288", "CIF 352×288"], ["416x240", "WQVGA 416×240"]]);
  const prot = protectionPicker("dmb", () => bitrate.value, "EEP_A", 3);
  const videoBox = h("div", { class: "grid-3" }, field("Picture size", size), field("Frame rate", fps), field("Video bitrate (kbps, max)", vbr, { hint: "Lowered automatically to what fits." }));
  const sync = () => { videoBox.classList.toggle("hidden", kind.value !== "tv"); if (kind.value === "tv" && parseInt(bitrate.value) < 256) bitrate.value = 448; prot.calc(); };
  kind.addEventListener("change", sync); bitrate.addEventListener("input", () => prot.calc()); sync();
  const m = modal({ title: "Add DMB service", wide: true, body: h("div", { class: "stack" },
    h("div", { class: "banner amber" }, icon("alert"), h("div", { class: "grow" }, "DMB uses a lot of capacity and few receivers outside Korea decode it. The manager packs the stream as T-DMB (MPEG-4 Systems) and adds the Reed-Solomon outer coding that current odr-dabmux no longer does.")),
    h("div", { class: "grid-3" }, field("Kind", kind), field("Label", label, { max: 16 }), field("Service id", sid)),
    field("Source (anything ffmpeg can read)", src, { hint: "Files, http/HLS/RTMP/SRT streams, capture devices or ffmpeg test sources." }),
    h("div", { class: "grid-2" }, field("Input format (-f)", ifmt), field("Input options", iopts, { hint: "Passed to ffmpeg before -i." })),
    h("div", { class: "grid-2" }, field("Subchannel bitrate (kbps)", bitrate, { hint: "Video + audio + T-DMB packaging overhead must fit." }), field("Audio bitrate (kbps)", abr)),
    videoBox, prot.el),
  foot: [btn("Cancel", { onclick: () => m.close() }), btn("Add", { cls: "primary", onclick: async () => {
    try {
      await api("POST", "/api/dmb", { kind: kind.value, label: label.value, sid: sid.value, source: src.value, bitrate: parseInt(bitrate.value), video_bitrate: parseInt(vbr.value), size: size.value,
        input_format: ifmt.value || undefined, input_opts: iopts.value || undefined, fps: parseInt(fps.value), audio_bitrate: abr.value ? parseInt(abr.value) : undefined,
        profile: prot.prof.value === "UEP" ? "EEP_A" : prot.prof.value, protection: parseInt(prot.lvl.value) });
      toast("DMB service staged.", "ok"); m.close(); pokeStatus(); route();
    } catch (e) { /* toasted */ }
  } })] });
}

/* ============================== mux settings (outputs/general/remotecontrol) ============================== */

async function pageOutputs(root) {
  setCrumbs("Mux settings");
  const [gen, rc, out] = await Promise.all([api("GET", "/api/section/general"), api("GET", "/api/section/remotecontrol"), api("GET", "/api/section/outputs")]);
  const ro = !isEditor();
  const g = (k, attrs = {}) => bind(gen, k, inp(gen[k] ?? "", { disabled: ro, ...attrs }));
  const r = (k, attrs = {}) => bind(rc, k, inp(rc[k] ?? "", { disabled: ro, ...attrs }));
  const outText = h("textarea", { rows: 14, class: "mono", disabled: ro });
  outText.value = JSON.stringify(out, null, 2);
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Mux settings"), h("p", null, "General, remote control and output settings of odr-dabmux."))),
    h("div", { class: "card card-pad stack" }, h("h3", null, "General"),
      h("div", { class: "grid-4" }, field("DAB mode", g("dabmode")), field("Frames (0 = forever)", g("nbframes")), field("Syslog", g("syslog")), field("Timestamps (tist)", g("tist"))),
      h("div", { class: "grid-2" }, field("Management port", g("managementport"), { hint: "The monitor reads levels and buffer states from here." }), field("TIST offset", g("tist_offset"))),
      ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save general", { cls: "primary", onclick: () => saveSection("general", gen) }))),
    h("div", { class: "card card-pad stack mt" }, h("h3", null, "Remote control"),
      h("div", { class: "grid-2" }, field("Telnet port", r("telnetport")), field("ZMQ endpoint", r("zmqendpoint", { class: "mono" }))),
      ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save remote control", { cls: "primary", onclick: () => saveSection("remotecontrol", rc) }))),
    h("div", { class: "card card-pad stack mt" }, h("h3", null, "Outputs"), h("p", { class: "small muted" }, "Edited as JSON (blocks become { }, values are strings). Outputs are where the modulator gets the mux from."),
      outText, ro ? null : h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Save outputs", { cls: "primary", onclick: () => { let v; try { v = JSON.parse(outText.value); } catch (e) { return toast("That is not valid JSON.", "error"); } saveSection("outputs", v); } }))));
}

/* ============================== checks ============================== */

async function pageChecks(root) {
  setCrumbs("Checks");
  const r = await api("GET", "/api/checks");
  const by = (s) => r.issues.filter((i) => i.severity === s);
  const dmOut = h("div");
  const testBtn = isEditor() ? btn("Test with odr-dabmux", { icon: "play", onclick: async () => {
    testBtn.disabled = true; put(clear(dmOut), h("div", { class: "banner blue" }, h("span", { class: "spin" }), "Running odr-dabmux on a sandboxed copy…"));
    try {
      const r = await api("POST", "/api/checks/dabmux", {});
      put(clear(dmOut), h("div", { class: "banner " + (r.skipped ? "amber" : r.ok ? "green" : "red") }, icon(r.ok ? "check" : "alert"), h("div", { class: "grow" }, r.message)),
        r.log ? h("details", null, h("summary", null, "odr-dabmux output"), h("div", { class: "code log" }, r.log)) : null);
    } finally { testBtn.disabled = false; }
  } }) : null;
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Checks"), h("p", null, "Problems found in the configuration as it will be after Apply. Apply also test-runs odr-dabmux on the new config and refuses to write one it rejects.")),
    h("span", { class: "spacer" }), testBtn), dmOut,
    h("div", { class: "stats" }, ["error", "warning", "info"].map((s) => h("div", { class: "stat" }, h("span", null, s === "error" ? "Errors" : s === "warning" ? "Warnings" : "Notes"), h("b", null, by(s).length)))),
    h("div", { class: "section-gap" }), issueList(r.issues));
}

/* ============================== changes / apply / history ============================== */

// Shows live progress of an Apply/rollback while `promise` runs. Returns the promise's result.
async function withProgress(title, promise) {
  const stepsEl = h("div", { class: "steps-list" });
  const clock = h("span", { class: "muted mono" }, "0s");
  const body = h("div", { class: "stack" },
    h("div", { class: "row" }, h("span", { class: "spin" }), h("b", { class: "grow" }, "Working…"), clock),
    stepsEl, h("p", { class: "small muted" }, "Keep this page open. The mux keeps running while the files are written; with a full supervisor restart every station drops for a few seconds."));
  const back = h("div", { class: "modal-back" });
  back.appendChild(h("div", { class: "modal", role: "dialog", "aria-modal": "true" }, h("div", { class: "modal-head" }, h("h2", null, title)), h("div", { class: "modal-body" }, body)));
  document.body.appendChild(back);
  const t0 = Date.now();
  let stop = false;
  const tick = async () => {
    if (stop) return;
    clock.textContent = `${Math.round((Date.now() - t0) / 1000)}s`;
    try {
      const pr = await api("GET", "/api/apply/progress", undefined, { quiet: true });
      if (pr.started && pr.steps) {
        clear(stepsEl);
        pr.steps.forEach((st, i) => {
          const last = i === pr.steps.length - 1 && pr.running;
          stepsEl.appendChild(h("div", { class: "step-row" + (last ? " active" : "") },
            last ? h("span", { class: "spin" }) : icon("check"), h("span", { class: "grow" }, st.text),
            h("span", { class: "muted mono small" }, last ? `${Math.round(pr.now - st.ts)}s` : (st.secs != null ? `${st.secs}s` : ""))));
        });
      }
    } catch (e) { /* the server may be busy restarting things */ }
    if (!stop) setTimeout(tick, 700);
  };
  tick();
  try { return await promise; } finally { stop = true; back.remove(); }
}

async function pageChanges(root) {
  setCrumbs("Changes & history");
  const [d, b] = await Promise.all([api("GET", "/api/draft"), api("GET", "/api/backups")]);
  const diffs = h("div", { class: "stack" }, d.diff.map((f) => h("details", { open: true }, h("summary", { class: "mono" }, f.path + (f.new ? " (new file)" : "")), diffView(f.diff))));
  const fsOps = (d.fs || []).filter((o) => o.op !== "stop_program");
  const apply = async (force = false) => {
    try {
      const r = await withProgress("Applying", api("POST", "/api/apply", { force }, { quiet: true }));
      showResult(r);
    } catch (e) {
      if (e.status === 409) {
        const r2 = await fetch("/api/apply", { method: "POST", headers: { "X-Requested-With": "odr-mux", "X-CSRF-Token": S.csrf, "Content-Type": "application/json" }, body: JSON.stringify({ force }) }).then((x) => x.json());
        if (r2.dabmux) {
          // odr-dabmux itself refused the config: don't offer "apply anyway"
          modal({ title: "odr-dabmux would not start with this config", wide: true, body: h("div", { class: "stack" },
            h("div", { class: "banner red" }, icon("alert"), h("div", { class: "grow" }, r2.message)),
            h("p", null, "Nothing was written; the running mux is untouched. Fix the setting under Checks / the relevant page and apply again."),
            r2.log ? h("details", null, h("summary", null, "odr-dabmux output"), h("div", { class: "code log" }, r2.log)) : null) });
          return;
        }
        const m = modal({ title: "Apply anyway?", body: h("div", { class: "stack" }, h("p", null, r2.message), issueList(r2.errors || [])),
          foot: [btn("Cancel", { onclick: () => m.close() }), btn("Apply anyway", { cls: "danger", onclick: () => { m.close(); apply(true); } })] });
      } else toast(e.message, "error");
    }
  };
  const showResult = (r) => {
    const m = modal({ title: r.ok ? "Applied" : "Apply had problems", body: h("div", { class: "stack" }, h("div", { class: "banner " + (r.ok ? "green" : "red") }, icon(r.ok ? "check" : "alert"), r.message),
      r.warning ? h("div", { class: "banner amber" }, icon("alert"), h("div", { class: "grow" }, r.warning)) : null,
      h("div", { class: "code log" }, (r.log || []).join("\n"))), foot: btn("Close", { cls: "primary", onclick: () => { m.close(); pokeStatus(); route(); } }) });
  };
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Changes & history"), h("p", null, "Review what Apply will write, apply it, or roll back."))),
    d.pending ? h("div", { class: "card card-pad stack" },
      d.stale ? h("div", { class: "banner red" }, icon("alert"), "The files on disk changed since these edits started (someone edited them by hand). Applying will overwrite those changes. Discard the draft to start from the files on disk.") : null,
      h("div", { class: "row" }, h("h3", null, "Unapplied changes"), h("span", { class: "spacer" }),
        isEditor() ? btn("Discard", { cls: "ghost danger", icon: "trash", onclick: async () => { if (await confirmDialog("Throw away all unapplied changes?", { danger: true, okText: "Discard" })) { await api("POST", "/api/draft/discard", {}); pokeStatus(); route(); } } }) : null,
        isEditor() ? btn("Apply now", { cls: "primary", icon: "zap", onclick: async () => { if (await confirmDialog("Write the files and reload supervisor / odr-dabmux as set in Settings (reread/update, or a full supervisor restart)? A backup is taken first.", { okText: "Apply" })) apply(); } }) : null),
      h("ul", { class: "small" }, d.log.map((l) => h("li", null, `${fmtDate(l.ts)} · ${l.user}: ${l.summary}`))),
      fsOps.length ? h("div", { class: "banner amber" }, icon("folder"), h("div", { class: "grow" }, h("b", null, "Folder changes: "), h("ul", null, fsOps.map((o) => h("li", { class: "mono small" },
        o.op === "move_many" ? o.moves.map((mv) => `${mv.from} → ${mv.to}`).join("; ") : o.op === "archive" ? `archive ${o.path} → ${o.to}` : `${o.op} ${o.path}`))))) : null,
      diffs) : h("div", { class: "banner green" }, icon("check"), "No unapplied changes: the config files match what you see here."),
    h("div", { class: "section-gap" }), h("h2", null, "Backups"),
    h("div", { class: "card" }, h("div", { class: "table-wrap" }, h("table", null, h("thead", null, h("tr", null, h("th", null, "When"), h("th", null, "By"), h("th", null, "Files"), h("th", null, ""))),
      h("tbody", null, b.backups.length ? b.backups.map((x) => h("tr", null, h("td", null, fmtDate(x.ts)), h("td", null, x.user || ""), h("td", { class: "small mono" }, x.files.map((f) => f.split("/").pop()).join(", "),
        x.rolled_back ? h("span", { class: "chip amber" }, "rolled back") : null),
        h("td", { class: "nowrap" }, btn("Compare", { cls: "sm ghost", onclick: async () => { const r = await api("GET", `/api/backups/${x.id}/diff`); modal({ title: `Now vs backup ${x.id}`, wide: true, body: r.files.length ? h("div", { class: "stack" }, r.files.map((f) => h("details", { open: true }, h("summary", { class: "mono" }, f.path), diffView(f.diff)))) : h("p", null, "Identical to the current files.") }); } }),
          isEditor() ? btn("Roll back", { cls: "sm danger ghost", onclick: async () => { if (await confirmDialog(`Restore the files as they were before ${fmtDate(x.ts)}? Folder moves made by that apply are undone too, and supervisor/odr-dabmux are reloaded.`, { danger: true, okText: "Roll back" })) { const r = await withProgress("Rolling back", api("POST", `/api/backups/${x.id}/rollback`, {})); showResult(r); } } }) : null))) :
        h("tr", null, h("td", { colspan: 4, class: "muted" }, "No backups yet. One is made on every Apply.")))))));
}

function diffView(text) {
  const el = h("div", { class: "code diff" });
  for (const line of text.split("\n")) el.appendChild(h("div", { class: line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : line.startsWith("@@") ? "hunk" : "" }, line || " "));
  return el;
}

async function pageFiles(root) {
  setCrumbs("Config files");
  const which = location.hash.includes("live") ? "live" : "draft";
  const r = await api("GET", `/api/raw?which=${which}${S.revealSecrets && isAdmin() ? "&reveal=1" : ""}`);
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Config files"), h("p", null, which === "draft" ? "As they will be written on Apply." : "As they are on disk now.")),
    h("span", { class: "spacer" }), h("div", { class: "segmented" }, h("button", { class: which === "draft" ? "on" : "", onclick: () => { location.hash = "#/files"; } }, "After apply"), h("button", { class: which === "live" ? "on" : "", onclick: () => { location.hash = "#/files/live"; } }, "On disk"))),
    h("details", { open: true }, h("summary", { class: "mono" }, r.mux.path), codeBlock(r.mux.text)),
    r.supervisor.map((f) => h("details", null, h("summary", { class: "mono" }, f.path), codeBlock(f.text))));
}

/* ============================== import ============================== */

async function pageImport(root) {
  setCrumbs("Import / mux folder");
  let st = null;
  try { st = await api("GET", "/api/settings"); } catch (e) { /* not admin */ }
  const rootInp = inp((st && st.project_root) || "", { class: "mono", placeholder: "/home/ryan/dab" });
  const result = h("div", { class: "stack" });
  const scan = async (muxPath, sups) => {
    const r = await api("POST", "/api/import/scan", { root: rootInp.value, mux_path: muxPath, supervisor_paths: sups });
    const muxSel = sel(r.mux_path || "", r.mux_files.map((m) => [m, m.split("/").pop()]));
    const supBoxes = [...new Set([...r.supervisor_files, ...r.other_conf])].map((f) => [f, toggle(f, (sups || r.supervisor_files).includes(f))]);
    muxSel.addEventListener("change", () => scan(muxSel.value, supBoxes.filter((x) => x[1].box.checked).map((x) => x[0])));
    supBoxes.forEach(([, t]) => t.box.addEventListener("change", () => scan(muxSel.value, supBoxes.filter((x) => x[1].box.checked).map((x) => x[0]))));
    const p = r.preview;
    put(clear(result),
      !r.mux_files.length ? h("div", { class: "banner red" }, icon("alert"), "No .mux file in that folder.") : null,
      r.mux_files.length ? h("div", { class: "card card-pad stack" },
        field("Mux config", muxSel, { hint: "Other .mux files in the folder (test configs etc.) are left alone." }),
        h("div", { class: "field" }, h("label", null, "Supervisor files with the encoders"), h("div", { class: "list-check" }, supBoxes.map((x) => x[1].el))),
        p && p.error ? h("div", { class: "banner red" }, icon("alert"), p.error) : null,
        p && !p.error ? h("div", { class: "stack" },
          h("div", { class: "stats" }, [["Ensemble", p.ensemble || "?"], ["Stations", p.stations], ["Local encoders", p.local], ["External feeds", p.external], ["Data", p.data], ["CU", `${p.cu}/864`]].map(([k, v]) => h("div", { class: "stat" }, h("span", null, k), h("b", null, v)))),
          h("div", { class: "table-wrap" }, h("table", null, h("tbody", null, p.list.map((s) => h("tr", null, h("td", null, s.label), h("td", null, codecBadge(s.codec), ` ${s.bitrate}k`), h("td", null, s.feed), h("td", { class: "mono small" }, s.ptag || ""), h("td", { class: "mono small" }, s.audio_program || "")))))),
          p.issues.length ? h("details", null, h("summary", null, `${p.issues.length} things the checker noticed`), issueList(p.issues)) : null,
          h("div", { class: "banner blue" }, icon("info"), h("div", { class: "grow" }, "Importing changes nothing on disk. Stations that get their audio from another machine are marked external, and no encoders are created for them.")),
          h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Use this mux", { cls: "primary", icon: "import", onclick: async () => {
            await api("POST", "/api/import", { root: r.root, mux_path: muxSel.value, supervisor_paths: supBoxes.filter((x) => x[1].box.checked).map((x) => x[0]) });
            toast("Imported.", "ok"); S.configured = true; boot(); location.hash = "#/monitor";
          } }))) : null) : null);
  };
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Mux folder"), h("p", null, "Point the manager at the folder with conf.mux, supervisor/, mot/…"))),
    !isAdmin() ? h("div", { class: "banner amber" }, "Only administrators can change this.") :
      h("div", { class: "card card-pad stack" }, field("Folder", h("div", { class: "row" }, rootInp,
        btn("Browse", { cls: "ghost", icon: "folder", onclick: async () => { const f = await fileBrowser({ title: "Choose the mux folder", start: rootInp.value || "/" }); if (f) { rootInp.value = f; scan(); } } }),
        btn("Scan", { cls: "primary", icon: "search", onclick: () => scan() })))),
    h("div", { class: "section-gap" }), result);
  if (rootInp.value) scan();
}

/* ============================== users ============================== */

async function pageUsers(root) {
  setCrumbs("Users");
  const [u, st] = await Promise.all([api("GET", "/api/users"), S.configured ? api("GET", "/api/stations") : Promise.resolve({ stations: [] })]);
  const stations = st.stations;
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Users"), h("p", null, "Admins manage everything, editors change the mux, viewers see everything read-only, station monitors only see their own stations' levels, DLS and slides.")),
    h("span", { class: "spacer" }), btn("Add user", { cls: "primary", icon: "plus", onclick: () => userEditor(null, stations) })),
    h("div", { class: "card" }, h("table", null, h("thead", null, h("tr", null, ["User", "Role", "Stations", "Last login", ""].map((x) => h("th", null, x)))),
      h("tbody", null, u.users.map((x) => h("tr", { class: "click", onclick: () => userEditor(x, stations) }, h("td", null, h("b", null, x.display_name), h("div", { class: "small muted" }, x.username)),
        h("td", null, ROLE_LABEL[x.role], x.disabled ? h("span", { class: "chip red" }, "disabled") : null),
        h("td", { class: "small" }, x.role === "station" ? x.stations.map((k) => (stations.find((s) => s.id === k) || { label: k }).label).join(", ") || "none" : "all"),
        h("td", { class: "small" }, fmtAgo(x.last_login)), h("td", null, icon("edit"))))))));
}

function userEditor(u, stations) {
  const un = inp(u ? u.username : "", { disabled: !!u }), dn = inp(u ? u.display_name : "");
  const role = sel(u ? u.role : "viewer", Object.entries(ROLE_LABEL));
  const pw = h("input", { type: "password", autocomplete: "new-password", placeholder: u ? "leave empty to keep" : "" });
  const dis = toggle("Disabled", u && u.disabled);
  const cur = new Set(u ? u.stations : []);
  const boxes = stations.filter((s) => s.kind === "audio").map((s) => [s.id, toggle(`${s.label} (${s.id})`, cur.has(s.id))]);
  const stBox = h("div", { class: "field" }, h("label", null, "Stations this user may monitor"), h("div", { class: "list-check" }, boxes.map((b) => b[1].el)),
    h("div", { class: "hint" }, "They see levels, DLS, slides and whether the encoders run - nothing else, and nothing of other stations."));
  const sync = () => stBox.classList.toggle("hidden", role.value !== "station");
  role.addEventListener("change", sync); sync();
  const m = modal({ title: u ? `Edit ${u.username}` : "Add user", body: h("div", { class: "stack" },
    h("div", { class: "grid-2" }, field("Username", un), field("Display name", dn)), h("div", { class: "grid-2" }, field("Role", role), field(u ? "New password" : "Password", pw, { hint: "At least 10 characters. They must change it at first login." })),
    u ? dis.el : null, stBox),
  foot: [u ? btn("Delete", { cls: "danger ghost", onclick: async () => { if (await confirmDialog(`Delete ${u.username}?`, { danger: true, okText: "Delete" })) { await api("DELETE", `/api/users/${u.id}`); m.close(); route(); } } }) : null,
    h("span", { class: "spacer" }), btn("Cancel", { onclick: () => m.close() }),
    btn("Save", { cls: "primary", onclick: async () => {
      const body = { display_name: dn.value, role: role.value, stations: boxes.filter((b) => b[1].box.checked).map((b) => b[0]) };
      if (pw.value) body.password = pw.value;
      try {
        if (u) await api("PUT", `/api/users/${u.id}`, { ...body, disabled: dis.box.checked });
        else await api("POST", "/api/users", { ...body, username: un.value });
        m.close(); route();
      } catch (e) { /* toasted */ }
    } })] });
}

/* ============================== settings ============================== */

async function pageSettings(root) {
  setCrumbs("Settings");
  const s = await api("GET", "/api/settings");
  const caps = await api("GET", "/api/capabilities?refresh=1");
  S.caps = caps;
  const bindSel = sel(s.bind, [["127.0.0.1", "127.0.0.1 - this machine only (use with a reverse proxy or SSH tunnel)"], ["0.0.0.0", "0.0.0.0 - all network interfaces"]]);
  const port = inp(s.port, { type: "number", min: 1024, max: 65535 });
  const f = (k, attrs = {}) => inp(s[k] ?? "", attrs);
  const sock = f("supervisor_socket", { class: "mono" }), ctl = f("supervisorctl", { class: "mono" }), sconf = f("supervisor_conf", { class: "mono", placeholder: "default" });
  const restart = f("dabmux_restart", { class: "mono", placeholder: "auto" });
  const reloadMode = sel(s.supervisor_reload || "update", [["update", "reread + update: only changed programs restart"], ["restart", "restart the supervisor service: everything restarts"]]);
  const restartCmd = f("supervisor_restart_cmd", { class: "mono", placeholder: "sudo -n systemctl restart supervisor" });
  const sudoMode = sel(s.supervisor_sudo || "auto", [["auto", "use sudo supervisorctl when the socket is root-only"], ["always", "always use sudo supervisorctl"], ["never", "never use sudo"]]);
  const run = toggle("Run supervisor / odr-dabmux commands on Apply", s.run_commands);
  const vdm = toggle("Test-run the new config through odr-dabmux before Apply writes it", s.validate_with_dabmux !== false);
  const levels = sel(s.levels_source, [["dabmux", "odr-dabmux management port (no extra sockets)"], ["stats", "odr-audioenc --stats sockets"], ["both", "Both (encoder sockets when free)"]]);
  const mgmt = f("dabmux_mgmt", { class: "mono", placeholder: "from the mux file" }), onair = f("onair_edi", { class: "mono", placeholder: "auto" });
  const sdb = f("silence_db", { type: "number" }), ssec = f("silence_secs", { type: "number" });
  const statsDir = f("stats_dir", { class: "mono" }), encUser = f("encoder_user", { placeholder: "copied from existing programs" });
  const tp = s.tool_paths || {};
  const tools = ["odr-audioenc", "odr-padenc", "odr-dabmux", "ffmpeg"].map((t) => [t, inp(tp[t] || "", { class: "mono", placeholder: (caps.tools || {})[t] || "not found" })]);
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Settings"))),
    h("div", { class: "card card-pad stack" }, h("h3", null, "Network"),
      h("p", { class: "small muted" }, "Where the web UI listens. After saving, the service restarts on the new address; open it there within 60 seconds and confirm, or it goes back to the old one."),
      h("div", { class: "grid-2" }, field("Listen address", bindSel), field("Port", port, { hint: "Default 8092 (SPI generator uses 8090)." })),
      h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Change address", { cls: "primary", onclick: async () => {
        if (!(await confirmDialog(`Restart the web UI on ${bindSel.value}:${port.value}?`, { okText: "Restart" }))) return;
        try {
          const r = await api("PUT", "/api/network", { bind: bindSel.value, port: parseInt(port.value) });
          const host = bindSel.value === "127.0.0.1" ? "127.0.0.1" : location.hostname;
          const url = `${location.protocol}//${host}:${port.value}/#/settings/confirm/${r.token}`;
          modal({ title: "Confirm the new address", body: h("div", { class: "stack" }, h("p", null, "Open the new address and confirm within 60 seconds:"), codeBlock(url), h("a", { class: "btn primary", href: url }, "Open new address")) });
        } catch (e) { /* toasted */ }
      } }))),
    h("div", { class: "card card-pad stack mt" }, h("h3", null, "Control"),
      h("div", { class: "grid-3" }, field("supervisord socket", sock), field("supervisorctl", ctl), field("supervisord.conf", sconf)),
      h("div", { class: "grid-2" }, field("After Apply", reloadMode, { hint: "Restarting the service briefly takes every station off air." }), field("Service restart command", restartCmd)),
      field("Restart odr-dabmux with", restart, { hint: "auto (a supervisor program running odr-dabmux), none, supervisor:<program>, systemd:<unit> or command:<shell command>." }),
      field("Permissions", sudoMode, { hint: "The default supervisor socket is root-only; the installer adds a sudoers rule so the manager can use sudo -n supervisorctl." }),
      run.el, vdm.el),
    h("div", { class: "card card-pad stack mt" }, h("h3", null, "Monitoring"),
      h("div", { class: "grid-2" }, field("Audio levels from", levels), field("odr-dabmux management endpoint", mgmt)),
      h("div", { class: "grid-3" }, field("Silence below (dBFS)", sdb), field("…for (seconds)", ssec), field("On-air decoder (EDI output)", onair, { hint: "auto = the mux's EDI TCP output, off, or tcp://host:port." }))),
    h("div", { class: "card card-pad stack mt" }, h("h3", null, "New encoders"),
      h("div", { class: "grid-2" }, field("Stats socket folder", statsDir), field("Run encoders as user", encUser))),
    h("div", { class: "card card-pad stack mt" }, h("h3", null, "Tools"),
      h("dl", { class: "kv" }, h("dt", null, "odr-audioenc"), h("dd", null, caps.audioenc ? `${caps.audioenc.version || ""} · inputs: ${caps.inputs.join(", ") || "none"}` : "not found"),
        h("dt", null, "odr-dabmux"), h("dd", null, caps.dabmux ? caps.dabmux.version : "not found"), h("dt", null, "ffmpeg"), h("dd", null, caps.ffmpeg ? `found${caps.ffmpeg.libx264 ? " · libx264" : ""}${caps.ffmpeg.he_aac ? " · libfdk_aac" : ""}` : "not found")),
      h("div", { class: "grid-2" }, tools.map(([t, i]) => field(`${t} path`, i)))),
    updatesCard(),
    h("div", { class: "row mt" }, h("span", { class: "spacer" }), btn("Save settings", { cls: "primary", onclick: async () => {
      try {
        await api("PUT", "/api/settings", { supervisor_socket: sock.value, supervisorctl: ctl.value, supervisor_conf: sconf.value, dabmux_restart: restart.value || "auto", run_commands: run.box.checked,
          supervisor_reload: reloadMode.value, validate_with_dabmux: vdm.box.checked, supervisor_restart_cmd: restartCmd.value || "sudo -n systemctl restart supervisor", supervisor_sudo: sudoMode.value,
          levels_source: levels.value, dabmux_mgmt: mgmt.value, onair_edi: onair.value || "auto", silence_db: sdb.value, silence_secs: ssec.value, stats_dir: statsDir.value, encoder_user: encUser.value,
          tool_paths: Object.fromEntries(tools.map(([t, i]) => [t, i.value])) });
        toast("Saved.", "ok");
      } catch (e) { /* toasted */ }
    } })));
  const m = location.hash.match(/#\/settings\/confirm\/(.+)$/);
  if (m) { try { await api("POST", "/api/network/confirm", { token: m[1] }); toast("New address confirmed.", "ok"); location.hash = "#/settings"; } catch (e) { /* toasted */ } }
}

/* ============================== updates ============================== */

function updatesCard() {
  const body = h("div", { class: "stack" });
  const card = h("div", { class: "card card-pad stack mt" }, h("h3", null, "Updates"), body);
  let timer = null, wasRunning = false, startCommit = null;
  const draw = (u) => {
    const st = u.status || {};
    const running = u.pending || st.state === "running";
    const short = (c) => (c ? c.slice(0, 7) : "unknown");
    put(clear(body),
      h("dl", { class: "kv" },
        h("dt", null, "Installed"), h("dd", { class: "mono" }, `${u.version} (${short(u.commit)})`),
        h("dt", null, "Source"), h("dd", { class: "mono" }, u.configured ? `${u.repo} · ${u.branch}` : "not a git install"),
        st.checked_at ? [h("dt", null, "Last check"), h("dd", null, fmtAgo(st.checked_at))] : null),
      !u.configured ? h("div", { class: "banner amber" }, icon("info"), h("div", { class: "grow" }, "Updates from here need an install made from a git checkout: ", h("code", null, "git clone … && sudo ./install.sh"), ".")) :
        h("div", { class: "stack tight" },
          running ? h("div", { class: "banner blue" }, h("span", { class: "spin" }), h("div", { class: "grow" }, st.message || "Waiting for the updater…")) :
            st.state === "error" ? h("div", { class: "banner red" }, icon("alert"), h("div", { class: "grow" }, st.message)) :
            st.message ? h("div", { class: "banner " + (st.available ? "amber" : "green") }, icon(st.available ? "arrowUp" : "check"),
              h("div", { class: "grow" }, st.message, st.available && st.remote_commit ? ` (${short(st.remote_commit)})` : "")) : null,
          h("p", { class: "small muted" }, "Updating downloads the latest version from the source above and re-runs the installer with your current settings. The web UI restarts (the mux and encoders keep running); this page reconnects by itself."),
          h("div", { class: "row" }, h("span", { class: "spacer" }),
            btn("Check for updates", { icon: "refresh", disabled: running, onclick: () => req("check") }),
            btn("Update now", { cls: "primary", icon: "arrowUp", disabled: running || (st.remote_commit && !st.available && st.remote_commit === u.commit), onclick: async () => {
              if (await confirmDialog("Download and install the latest version? The web UI restarts for a moment; the mux keeps running.", { okText: "Update now" })) req("apply");
            } }))));
  };
  const load = async () => {
    let u;
    try { u = await api("GET", "/api/updates", undefined, { quiet: true }); }
    catch (e) { // service restarting during an update
      put(clear(body), h("div", { class: "banner blue" }, h("span", { class: "spin" }), "Installing; the web UI is restarting…"));
      timer = setTimeout(load, 2000); return;
    }
    if (startCommit === null) startCommit = u.commit;
    const running = u.pending || (u.status && u.status.state === "running");
    draw(u);
    if (wasRunning && !running) {
      if (u.commit !== startCommit) { toast("Updated. Reloading…", "ok"); setTimeout(() => location.reload(), 1200); return; }
    }
    wasRunning = running;
    if (running && document.body.contains(card)) timer = setTimeout(load, 1500);
  };
  const req = async (action) => {
    try { await api("POST", "/api/updates", { action }); wasRunning = true; load(); } catch (e) { /* toasted */ }
  };
  load();
  return card;
}

/* ============================== audit / account ============================== */

async function pageAudit(root) {
  setCrumbs("Audit log");
  const r = await api("GET", "/api/audit");
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, "Audit log"))),
    h("div", { class: "card" }, h("table", null, h("tbody", null, r.rows.map((x) => h("tr", null, h("td", { class: "small nowrap" }, fmtDate(x.ts)), h("td", null, x.username || "—"), h("td", { class: "mono small" }, x.action), h("td", { class: "small" }, x.target), h("td", { class: "small muted" }, x.ip)))))));
}

function pageAccount(root) {
  setCrumbs("Account");
  const cur = h("input", { type: "password", autocomplete: "current-password" }), p = h("input", { type: "password", autocomplete: "new-password" });
  put(root, h("div", { class: "page-head" }, h("div", null, h("h1", null, S.user.display_name || S.user.username), h("p", null, ROLE_LABEL[S.user.role]))),
    h("div", { class: "card card-pad stack" }, h("h3", null, "Change password"), h("div", { class: "grid-2" }, field("Current password", cur), field("New password", p)),
      h("div", { class: "row" }, h("span", { class: "spacer" }), btn("Change", { cls: "primary", onclick: async () => { try { await api("POST", "/api/account/password", { current: cur.value, new: p.value }); toast("Password changed.", "ok"); cur.value = p.value = ""; } catch (e) { /* toasted */ } } }))));
}

boot();
