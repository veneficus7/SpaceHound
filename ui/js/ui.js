/* Shared UI building blocks: modal, confirm, toast, context menu, tooltip,
   job progress dialog, selection model and the item actions (delete, move…). */

/* view registry - every file in js/views adds itself here */
const Views = {};

const UI = (() => {
  const overlayRoot = () => document.getElementById("overlay-root");
  const tipEl = () => document.getElementById("tooltip");

  /* ------------------------------------------------------------ tooltip */
  function tip(e, htmlStr) {
    const t = tipEl();
    t.innerHTML = htmlStr;
    t.classList.remove("hidden");
    const pad = 14;
    const r = t.getBoundingClientRect();
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - pad;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - pad;
    t.style.left = Math.max(6, x) + "px";
    t.style.top = Math.max(6, y) + "px";
  }
  function hideTip() { tipEl().classList.add("hidden"); }

  // delegated [data-tip] hover for charts and badges
  document.addEventListener("mousemove", (e) => {
    const t = e.target.closest && e.target.closest("[data-tip]");
    if (t) tip(e, t.getAttribute("data-tip"));
    else if (!e.target.closest || !e.target.closest("canvas")) hideTip();
  });

  /* ------------------------------------------------------------ modal */
  function modal({ title, body = "", icon: ic = "info", tone = "", actions = [], wide = false, onMount, dismissable = true }) {
    return new Promise((resolve) => {
      const ov = U.el(`<div class="overlay"><div class="modal ${wide ? "wide" : ""}">
        <div class="modal-head"><div class="mi ${tone}">${icon(ic, "lg")}</div><h3>${U.esc(title)}</h3>
          ${dismissable ? `<button class="btn ghost sm icon" data-x>${icon("x")}</button>` : ""}</div>
        <div class="modal-body"></div>
        ${actions.length ? `<div class="modal-foot"></div>` : ""}</div></div>`);
      const bodyEl = ov.querySelector(".modal-body");
      if (typeof body === "string" || (body && body.__raw)) bodyEl.innerHTML = String(body);
      else if (body) bodyEl.append(body);
      const close = (v) => { ov.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
      const foot = ov.querySelector(".modal-foot");
      actions.forEach((a) => {
        const b = U.el(`<button class="btn ${a.kind || ""}">${a.icon ? icon(a.icon, "sm") : ""}${U.esc(a.label)}</button>`);
        b.onclick = async () => {
          if (a.onClick) { const r = await a.onClick(ov, close); if (r === false) return; }
          close(a.value !== undefined ? a.value : a.label);
        };
        foot.append(b);
      });
      const onKey = (e) => {
        if (e.key === "Escape" && dismissable) close(null);
        if (e.key === "Enter" && actions.length && !e.target.matches("textarea")) {
          const primary = foot.querySelector(".btn.primary, .btn.danger");
          if (primary) primary.click();
        }
      };
      document.addEventListener("keydown", onKey);
      const x = ov.querySelector("[data-x]");
      if (x) x.onclick = () => close(null);
      if (dismissable) ov.addEventListener("mousedown", (e) => { if (e.target === ov) close(null); });
      overlayRoot().append(ov);
      if (onMount) onMount(ov, close);
    });
  }

  function confirm({ title, message, confirmLabel = "Continue", danger = false, icon: ic, details = "" }) {
    return modal({
      title, icon: ic || (danger ? "alert" : "info"), tone: danger ? "danger" : "",
      body: `<p>${message}</p>${details}`,
      actions: [
        { label: "Cancel", kind: "ghost", value: false },
        { label: confirmLabel, kind: danger ? "danger" : "primary", value: true },
      ],
    }).then((v) => v === true);
  }

  function prompt({ title, label, value = "", placeholder = "", confirmLabel = "OK" }) {
    return modal({
      title, icon: "folder",
      body: `<div class="field"><label>${U.esc(label)}</label><input class="input" id="prompt-in" value="${U.esc(value)}" placeholder="${U.esc(placeholder)}"></div>`,
      onMount: (ov) => setTimeout(() => ov.querySelector("#prompt-in").focus(), 30),
      actions: [
        { label: "Cancel", kind: "ghost", value: null },
        { label: confirmLabel, kind: "primary", onClick: (ov, close) => { close(ov.querySelector("#prompt-in").value.trim() || null); return false; } },
      ],
    });
  }

  /* ------------------------------------------------------------ toast */
  function toast(msg, kind = "good", ms = 4200) {
    const ic = { good: "check", bad: "alert", warn: "alert", info: "info" }[kind] || "info";
    const t = U.el(`<div class="toast ${kind}">${icon(ic)}<div>${msg}</div></div>`);
    document.getElementById("toast-root").append(t);
    setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 320); }, ms);
  }

  /* ------------------------------------------------------------ context menu */
  let menuEl = null;
  function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
  document.addEventListener("mousedown", (e) => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
  window.addEventListener("blur", closeMenu);

  function menu(e, items, header) {
    e.preventDefault();
    closeMenu();
    hideTip();
    const m = U.el(`<div class="ctxmenu">${header ? `<div class="hd">${U.esc(header)}</div>` : ""}</div>`);
    items.filter(Boolean).forEach((it) => {
      if (it === "-") { m.append(U.el(`<div class="sep"></div>`)); return; }
      const row = U.el(`<div class="mi ${it.danger ? "danger" : ""}">${icon(it.icon || "chev-right", "sm")}<span>${U.esc(it.label)}</span></div>`);
      row.onclick = () => { closeMenu(); it.onClick(); };
      m.append(row);
    });
    document.body.append(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.min(e.clientX, innerWidth - r.width - 8) + "px";
    m.style.top = Math.min(e.clientY, innerHeight - r.height - 8) + "px";
    menuEl = m;
  }

  /* ------------------------------------------------------------ job dialog */
  async function runJob(jobId, { title, icon: ic = "zap", describe, cancellable = true }) {
    let cancelled = false;
    let closeFn = null;
    const body = U.el(`<div><div class="progress" style="margin:10px 0 12px"><i style="width:0%"></i></div><div class="jd small text-2">Starting…</div></div>`);
    modal({
      title, icon: ic, body, dismissable: false,
      actions: cancellable ? [{ label: "Cancel", kind: "ghost", onClick: () => { cancelled = true; API.cancel_job(jobId); return false; } }] : [],
      onMount: (_ov, close) => { closeFn = close; },
    });
    try {
      const res = await waitJob(jobId, (st) => {
        const p = st.progress || {};
        let frac = null;
        if (p.total) frac = (p.done || 0) / p.total;
        if (p.bytes_total) frac = (p.bytes_done || 0) / p.bytes_total;
        const bar = body.querySelector(".progress > i");
        if (frac != null) { bar.style.width = Math.min(100, frac * 100) + "%"; bar.parentElement.classList.remove("indeterminate"); }
        else { bar.parentElement.classList.add("indeterminate"); bar.style.width = "0"; }
        body.querySelector(".jd").innerHTML = describe ? describe(p, st) : U.esc(p.current || p.phase || "Working…");
      });
      return res;
    } catch (err) {
      if (!cancelled && !err.cancelled) toast(U.esc(err.message), "bad", 7000);
      return null;
    } finally {
      if (closeFn) closeFn(null);
    }
  }

  return { tip, hideTip, modal, confirm, prompt, toast, menu, closeMenu, runJob };
})();

/* ================================================================== selection */
class Selection {
  constructor(onChange) { this.map = new Map(); this.onChange = onChange; }
  key(item) { return item.path; }
  has(item) { return this.map.has(this.key(item)); }
  toggle(item, on) {
    const k = this.key(item);
    if (on === undefined) on = !this.map.has(k);
    if (on) this.map.set(k, item); else this.map.delete(k);
    this.changed();
  }
  set(items) { this.map.clear(); items.forEach((i) => this.map.set(this.key(i), i)); this.changed(); }
  clear() { this.map.clear(); this.changed(); }
  get size() { return this.map.size; }
  get items() { return Array.from(this.map.values()); }
  get bytes() { return this.items.reduce((a, i) => a + (i.size || 0), 0); }
  get paths() { return Array.from(this.map.keys()); }
  changed() { if (this.onChange) this.onChange(this); }
}

/* render a floating selection bar into the view */
function renderSelBar(host, sel, buttons) {
  let bar = host.querySelector(":scope > .selbar");
  if (!sel.size) { if (bar) bar.remove(); return; }
  if (!bar) { bar = U.el(`<div class="selbar"></div>`); host.append(bar); }
  bar.innerHTML = `<div class="what">${U.num(sel.size)} selected<span>${U.bytes(sel.bytes)}</span></div><div class="spacer"></div>`;
  buttons.forEach((b) => {
    const el = U.el(`<button class="btn ${b.kind || ""} sm">${b.icon ? icon(b.icon, "sm") : ""}${U.esc(b.label)}</button>`);
    el.onclick = b.onClick;
    bar.append(el);
  });
  const clear = U.el(`<button class="btn ghost sm icon" title="Clear selection">${icon("x", "sm")}</button>`);
  clear.onclick = () => sel.clear();
  bar.append(clear);
}

/* ================================================================== actions */
const Actions = {
  async delete(items, { mode, source = "manual" } = {}) {
    items = items.filter((i) => i && i.path);
    if (!items.length) return null;
    mode = mode || App.settings.delete_mode || "recycle";
    const paths = items.map((i) => i.path);
    const total = items.reduce((a, i) => a + (i.size || 0), 0);
    const checks = await API.check_paths(paths);
    const blocked = checks.filter((c) => c.level === "blocked");
    const warned = checks.filter((c) => c.level === "warn");
    const okCount = paths.length - blocked.length;
    const list = items.slice(0, 200).map((i) => `<div><span>${U.esc(i.path)}</span><b>${U.bytes(i.size || 0)}</b></div>`).join("");
    let details = `<div class="path-list">${list}${items.length > 200 ? `<div class="muted">…and ${items.length - 200} more</div>` : ""}</div>`;
    if (blocked.length) details += `<div class="notice bad">${icon("shield", "sm")}<div><b>${blocked.length} protected item(s) will be skipped.</b><div class="t">${U.esc(blocked[0].reason)}${blocked.length > 1 ? "…" : ""}</div></div></div>`;
    if (warned.length) details += `<div class="notice warn">${icon("alert", "sm")}<div><b>Careful:</b> <span class="t">${U.esc(warned[0].reason)}.</span></div></div>`;
    if (mode === "recycle") details += `<div class="notice info">${icon("info", "sm")}<div class="t">Items go to the Recycle Bin, so you can restore them. Space is freed once you empty the bin.</div></div>`;
    else details += `<div class="notice bad">${icon("alert", "sm")}<div class="t"><b>This can't be undone.</b> Files are deleted permanently and won't appear in the Recycle Bin.</div></div>`;
    if (!okCount) {
      await UI.modal({ title: "Nothing to delete", icon: "shield", tone: "warn", body: details, actions: [{ label: "OK", kind: "primary" }] });
      return null;
    }
    const ok = await UI.confirm({
      title: mode === "recycle" ? `Move ${U.num(okCount)} item(s) to the Recycle Bin?` : `Permanently delete ${U.num(okCount)} item(s)?`,
      message: `This frees up to <b>${U.bytes(total)}</b>.`,
      confirmLabel: mode === "recycle" ? "Move to Recycle Bin" : "Delete permanently",
      danger: true, icon: mode === "recycle" ? "trash" : "trash-x", details,
    });
    if (!ok) return null;
    const jobId = await API.start_delete(paths, mode, source);
    const res = await UI.runJob(jobId, {
      title: mode === "recycle" ? "Moving to Recycle Bin" : "Deleting", icon: "trash",
      describe: (p) => `${U.num(p.done || 0)} / ${U.num(p.total || 0)} · ${U.bytes(p.freed || 0)}`,
    });
    if (!res) return null;
    if (res.deleted) {
      if (mode !== "recycle" && res.freed > 50 * 1024 * 1024) FX.confetti();
      UI.toast(mode === "recycle"
        ? `Moved <b>${U.num(res.deleted)}</b> item(s) to the Recycle Bin (${U.bytes(res.freed)}).`
        : `Deleted <b>${U.num(res.deleted)}</b> item(s), freed <b>${U.bytes(res.freed)}</b>.`, "good");
    }
    if (res.failed && res.failed.length) {
      UI.modal({
        title: `${res.failed.length} item(s) could not be deleted`, icon: "alert", tone: "warn",
        body: `<div class="path-list">${res.failed.slice(0, 100).map((f) => `<div><span>${U.esc(f.path)}</span><b class="warn-t">${U.esc(f.error)}</b></div>`).join("")}</div>
               <p class="small">Files can be locked by running programs. Close them (or restart) and try again.</p>`,
        actions: [{ label: "OK", kind: "primary" }],
      });
    }
    App.afterChange();
    return res;
  },

  async move(items) {
    items = items.filter((i) => i && i.path);
    if (!items.length) return;
    let dest = null;
    if (App.info.mode === "webview") dest = await API.pick_folder();
    else dest = await UI.prompt({ title: "Move to…", label: "Destination folder", placeholder: "D:\\Archive", confirmLabel: "Move" });
    if (!dest) return;
    const total = items.reduce((a, i) => a + (i.size || 0), 0);
    const ok = await UI.confirm({
      title: `Move ${items.length} item(s)?`, icon: "move",
      message: `${U.bytes(total)} will be moved to <b>${U.esc(dest)}</b>. Moving to another drive frees space on this one.`,
      confirmLabel: "Move",
    });
    if (!ok) return;
    const jobId = await API.start_move(items.map((i) => i.path), dest);
    const res = await UI.runJob(jobId, { title: "Moving files", icon: "move", describe: (p) => `${U.num(p.done || 0)} / ${U.num(p.total || 0)} · ${U.esc(U.basename(p.current || ""))}` });
    if (!res) return;
    if (res.moved.length) UI.toast(`Moved <b>${res.moved.length}</b> item(s) (${U.bytes(res.size)}) to ${U.esc(dest)}.`, "good");
    if (res.failed.length) UI.toast(`${res.failed.length} item(s) failed: ${U.esc(res.failed[0].error)}`, "warn", 7000);
    App.afterChange();
  },

  reveal(path) { API.reveal(path); },
  open(path) { API.open_path(path); },
  async copy(text) {
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (_) { ok = await API.copy_text(text); }
    UI.toast(ok ? "Path copied to clipboard" : "Could not copy", ok ? "good" : "bad", 2000);
  },

  async refresh(id) {
    const jobId = await API.refresh_folder(id);
    const res = await UI.runJob(jobId, { title: "Rescanning folder", icon: "refresh", describe: (p) => `${U.num(p.files || 0)} files · ${U.esc(p.current || "")}` });
    if (res) { UI.toast("Folder rescanned", "good", 2000); App.afterChange(); }
  },

  /* standard context menu for files/folders */
  itemMenu(e, item, extra = []) {
    const isDir = item.type === "dir";
    UI.menu(e, [
      isDir && item.id != null ? { label: "Open in Explorer view", icon: "folder-open", onClick: () => App.go("explorer", { node: item.id }) } : null,
      isDir && item.id != null ? { label: "Show on Visual map", icon: "map", onClick: () => App.go("map", { node: item.id }) } : null,
      !isDir ? { label: "Open file", icon: "external", onClick: () => Actions.open(item.path) } : { label: "Open folder", icon: "external", onClick: () => Actions.open(item.path) },
      { label: "Show in File Explorer", icon: "folder", onClick: () => Actions.reveal(item.path) },
      { label: "Copy path", icon: "copy", onClick: () => Actions.copy(item.path) },
      isDir && item.id != null ? { label: "Find duplicates in here", icon: "files", onClick: () => App.go("duplicates", { roots: [item.path] }) } : null,
      isDir && item.id != null ? { label: "Rescan this folder", icon: "refresh", onClick: () => Actions.refresh(item.id) } : null,
      ...extra,
      "-",
      { label: "Move to…", icon: "move", onClick: () => Actions.move([item]) },
      { label: "Move to Recycle Bin", icon: "trash", danger: true, onClick: () => Actions.delete([item], { mode: "recycle" }) },
      { label: "Delete permanently", icon: "trash-x", danger: true, onClick: () => Actions.delete([item], { mode: "permanent" }) },
    ], item.path);
  },
};

/* small rendering helpers shared by views */
const R = {
  catBadge(cat) {
    const c = App.cats[cat];
    if (!c) return "";
    return `<span class="badge" style="background:${U.hexToRgba(c.color, 0.14)};color:${c.color}">${U.esc(c.label)}</span>`;
  },
  fileIcon(cat) {
    const c = App.cats[cat] || { color: "#6b7385" };
    return `<div class="ico" style="background:${U.hexToRgba(c.color, 0.15)};color:${c.color}">${icon(CAT_ICONS[cat] || "file")}</div>`;
  },
  dirIcon() { return `<div class="ico dir">${icon("folder")}</div>`; },
  sizeBar(frac, color) {
    return `<div class="bar"><i style="width:${Math.max(0.5, Math.min(100, frac * 100))}%;${color ? `background:${color}` : ""}"></i></div>`;
  },
  empty(ic, title, text, btn = "") {
    return `<div class="empty-state fade-in"><div class="ei">${icon(ic, "xl")}</div><h3>${U.esc(title)}</h3><p>${text}</p>${btn}</div>`;
  },
  needScan(what) {
    return R.empty("search", "Scan first", `Run a scan to see ${U.esc(what)}.`,
      `<button class="btn primary" onclick="App.openScanMenu(event)">${icon("play", "sm")}Start a scan</button>`);
  },
  loading(text = "Loading…") {
    return `<div class="empty-state"><div class="spinner lg" style="margin:0 auto 14px"></div><p>${U.esc(text)}</p></div>`;
  },
  ageClass(days) { return days > 365 ? "bad-t" : days > 90 ? "warn-t" : "good-t"; },
};
