/* App shell: state, navigation, top bar, scan lifecycle. Views register in Views (ui.js). */

const NAV = [
  ["Analyze", ["overview", "explorer", "map", "largest", "types", "old"]],
  ["Clean up", ["cleanup", "duplicates", "devjunk", "empty"]],
  ["Track", ["history", "apps", "activity"]],
];

const App = {
  info: null,
  settings: {},
  cats: {},
  catList: [],
  catKeys: [],
  summary: null,
  drives: [],
  view: null,
  params: {},
  scan: null,           // {id, status}
  state: {},            // per-view memory (filters, results) kept while switching views
  _cleanup: null,

  async init() {
    await API.ready;
    this.info = await API.app_info();
    this.settings = this.info.settings;
    this.catList = this.info.categories;
    this.catKeys = this.catList.map((c) => c.key);
    this.catList.forEach((c) => (this.cats[c.key] = c));
    this.cats.small = { key: "small", label: "Small files", color: "#4b5563" };
    this.applyTheme();
    this.renderSidebar();
    this.bindKeys();
    try { this.drives = await API.list_drives(); } catch (_) { this.drives = []; }
    if (this.info.has_scan) this.summary = await API.scan_summary();
    this.go("overview");
    if (this.info.start_paths && this.info.start_paths.length) this.startScan(this.info.start_paths);
  },

  catLabel(k) { return (this.cats[k] && this.cats[k].label) || "Other"; },

  /* ------------------------------------------------------------ theme */
  applyTheme() {
    const t = this.settings.theme || "dark";
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const resolved = t === "system" ? (mq.matches ? "light" : "dark") : t;
    document.documentElement.setAttribute("data-theme", resolved);
    if (!this._mqBound) { mq.addEventListener("change", () => this.settings.theme === "system" && this.applyTheme()); this._mqBound = true; }
  },
  async toggleTheme() {
    const cur = document.documentElement.getAttribute("data-theme");
    this.settings = await API.save_settings({ theme: cur === "dark" ? "light" : "dark" });
    this.applyTheme();
    this.renderTop();
    if (this.view === "map" || this.view === "overview") this.render();
  },

  /* ------------------------------------------------------------ navigation */
  go(view, params = {}) {
    if (!Views[view]) view = "overview";
    if (typeof this._cleanup === "function") { try { this._cleanup(); } catch (_) {} }
    this._cleanup = null;
    this.view = view;
    this.params = params;
    UI.hideTip();
    UI.closeMenu();
    this.renderSidebar();
    this.render();
  },

  async render() {
    const v = Views[this.view];
    this.renderTop();
    const banner = document.getElementById("scan-banner");
    if (banner) banner.classList.toggle("hidden", this.view === "overview");
    FX.stopBlips();
    const host = document.getElementById("view");
    host.scrollTop = 0;
    host.innerHTML = "";
    if (v.needsScan && !this.summary) {
      host.innerHTML = `<div class="page">${R.needScan(v.what || v.title.toLowerCase())}</div>`;
      return;
    }
    try {
      const cleanup = await v.render(host, this.params || {});
      if (typeof cleanup === "function") this._cleanup = cleanup;
    } catch (err) {
      console.error(err);
      host.innerHTML = `<div class="page">${R.empty("alert", "Something went wrong", U.esc(err.message || String(err)))}</div>`;
    }
  },

  /* re-render the current view after deletions etc. without losing params */
  async afterChange() {
    try { this.summary = await API.scan_summary(); } catch (_) {}
    try { this.drives = await API.list_drives(); } catch (_) {}
    try { const info = await API.app_info(); this.info.freed_total = info.freed_total; } catch (_) {}
    this.renderSidebar();
    const v = Views[this.view];
    if (v && v.refresh) v.refresh();
    else this.render();
  },

  renderSidebar() {
    const nav = document.getElementById("nav");
    let html = "";
    for (const [group, items] of NAV) {
      html += `<div class="nav-group">${group}</div>`;
      for (const id of items) {
        const v = Views[id];
        if (!v) continue;
        const dim = v.needsScan && !this.summary;
        const badge = v.badge ? v.badge() : "";
        html += `<div class="nav-item ${this.view === id ? "active" : ""} ${dim ? "disabled" : ""}" data-nav="${id}">
          ${icon(v.icon)}<span>${U.esc(v.title)}</span>${badge ? `<span class="count">${badge}</span>` : ""}</div>`;
      }
    }
    html += `<div class="nav-group">App</div><div class="nav-item ${this.view === "settings" ? "active" : ""}" data-nav="settings">${icon("settings")}<span>Settings</span></div>`;
    nav.innerHTML = html;
    nav.querySelectorAll("[data-nav]").forEach((el) => (el.onclick = () => this.go(el.dataset.nav)));
    const foot = document.getElementById("side-foot");
    const freed = this.info ? this.info.freed_total || 0 : 0;
    const h = this.summary && this.summary.health;
    foot.innerHTML = `
      ${h ? `<div class="mini-drive" id="mini-drive" title="Disk health">${Charts.ring(h.used / (h.total || 1), { size: 36, stroke: 4 })}
        <div style="min-width:0"><div class="t">${U.bytes(h.free)} free</div><div class="s">Health ${h.score}/100 · ${U.esc(h.label)}</div></div></div>` : ""}
      ${freed > 0 ? `<div class="freed-box"><b>${U.bytes(freed)}</b><span>freed with SpaceHound</span></div>` : ""}
      ${this.info && !this.info.admin && this.info.platform === "win32" ? `<button class="btn sm" id="elevate" title="See system folders that need admin rights">${icon("shield", "sm")}Run as administrator</button>`
        : `<div class="muted small" style="padding:0 2px">v${this.info ? this.info.version : ""} · Administrator</div>`}`;
    const el = document.getElementById("elevate");
    if (el) el.onclick = () => this.elevate();
    const md = document.getElementById("mini-drive");
    if (md) md.onclick = () => this.go("overview");
  },

  async elevate() {
    const ok = await UI.confirm({ title: "Restart as administrator?", icon: "shield",
      message: "SpaceHound will restart with admin rights so it can measure system folders (Windows, other users, System Volume Information). Current results will be lost." ,
      confirmLabel: "Restart" });
    if (!ok) return;
    const started = await API.elevate();
    if (!started) UI.toast("Elevation was cancelled.", "warn");
  },

  renderTop() {
    const v = Views[this.view] || {};
    const top = document.getElementById("topbar");
    const s = this.summary;
    const sub = this.subtitle || (s ? `${s.roots.join(", ")} · ${U.bytes(s.size)} · ${U.num(s.files)} files · scanned ${U.ago(s.finished)}` : "No scan yet");
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    top.innerHTML = `
      <div class="top-title"><h1>${U.esc(v.title || "")}</h1><div class="sub">${U.esc(sub)}</div></div>
      <div class="search-box">${icon("search", "sm")}<input id="gsearch" placeholder="Search files & folders…" ${s ? "" : "disabled"} value="${U.esc(this.view === "search" ? this.params.q || "" : "")}"><kbd>Ctrl F</kbd></div>
      <button class="btn ghost icon" id="palbtn" title="Command palette (Ctrl K)">${icon("zap")}</button>
      ${s ? `<button class="btn" id="rescan" title="Scan the same location again (F5)">${icon("refresh", "sm")}Rescan</button>` : ""}
      <button class="btn primary" id="scanbtn">${icon("play", "sm")}Scan${icon("chev-down", "sm")}</button>
      <button class="btn ghost icon" id="themebtn" title="Toggle theme">${icon(dark ? "sun" : "moon")}</button>`;
    this.subtitle = null;
    top.querySelector("#scanbtn").onclick = (e) => this.openScanMenu(e);
    top.querySelector("#themebtn").onclick = () => this.toggleTheme();
    top.querySelector("#palbtn").onclick = () => Palette.toggle();
    const rs = top.querySelector("#rescan");
    if (rs) rs.onclick = () => this.startScan(s.roots);
    const gs = top.querySelector("#gsearch");
    gs.onkeydown = (e) => { if (e.key === "Enter" && gs.value.trim()) this.go("search", { q: gs.value.trim() }); };
  },

  setSubtitle(text) {
    const el = document.querySelector("#topbar .sub");
    if (el) el.textContent = text;
  },

  bindKeys() {
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); Palette.toggle(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        const gs = document.getElementById("gsearch");
        if (gs && !gs.disabled) { e.preventDefault(); gs.focus(); gs.select(); }
      }
      if (e.key === "F5") { e.preventDefault(); if (this.summary) this.startScan(this.summary.roots); }
      if (e.key === "Backspace" && !e.target.matches("input, textarea, select")) {
        const v = Views[this.view];
        if (v && v.up) { e.preventDefault(); v.up(); }
      }
    });
    document.addEventListener("contextmenu", (e) => {
      if (!e.target.closest("input, textarea, [data-allow-ctx]")) e.preventDefault();
    });
  },

  /* ------------------------------------------------------------ scanning */
  openScanMenu(e) {
    const items = this.drives.filter((d) => d.ready).map((d) => ({
      label: `${d.path}  ${d.label ? "(" + d.label + ")" : ""} — ${U.bytes(d.used)} used`, icon: "drive",
      onClick: () => this.startScan([d.path]),
    }));
    const fixed = this.drives.filter((d) => d.ready && d.type === "fixed");
    UI.menu(e, [
      ...items,
      fixed.length > 1 ? { label: "All local drives", icon: "layers", onClick: () => this.startScan(fixed.map((d) => d.path)) } : null,
      "-",
      { label: "Choose a folder…", icon: "folder-open", onClick: () => this.chooseFolder() },
      { label: "My user folder", icon: "folder", onClick: () => this.startScan([this.info.home]) },
    ], "What should SpaceHound scan?");
  },

  async chooseFolder() {
    let p = null;
    if (this.info.mode === "webview") p = await API.pick_folder();
    else p = await UI.prompt({ title: "Scan a folder", label: "Folder path", placeholder: "C:\\Users\\you\\Videos", confirmLabel: "Scan" });
    if (p) this.startScan([p]);
  },

  async startScan(paths) {
    if (this.scan) await API.cancel_job(this.scan.id);
    let id;
    try { id = await API.start_scan(paths); }
    catch (err) { UI.toast(U.esc(err.message), "bad"); return; }
    this.scan = { id, paths, status: null };
    this.showScanBanner();
    if (this.view !== "overview") this.go("overview");
    else this.render();
    try {
      await waitJob(id, (st) => { this.scan.status = st; this.updateScanBanner(); }, 200);
      if (this.scan && this.scan.id !== id) return;
      this.summary = await API.scan_summary();
      this.state = {};
      this.scan = null;
      this.hideScanBanner();
      this.renderSidebar();
      UI.toast(`Scan complete: <b>${U.bytes(this.summary.size)}</b> in ${U.num(this.summary.files)} files (${U.duration(this.summary.duration)}).`, "good");
      this.go("overview");
    } catch (err) {
      if (this.scan && this.scan.id !== id) return;
      this.scan = null;
      this.hideScanBanner();
      if (!err.cancelled) UI.toast(U.esc(err.message), "bad", 7000);
      this.render();
    }
  },

  showScanBanner() {
    this.hideScanBanner();
    const b = U.el(`<div class="scan-banner" id="scan-banner">
      <div class="spinner"></div>
      <div class="meta"><div><b>Scanning ${U.esc(this.scan.paths.join(", "))}</b> <span class="muted" id="sb-stats"></span></div>
      <div class="cur" id="sb-cur">Starting…</div><div class="indeterminate"></div></div>
      <button class="btn sm" id="sb-cancel">${icon("stop", "sm")}Stop</button></div>`);
    document.getElementById("topbar").after(b);
    b.classList.toggle("hidden", this.view === "overview");
    b.querySelector("#sb-cancel").onclick = () => { if (this.scan) API.cancel_job(this.scan.id); };
  },
  updateScanBanner() {
    const st = this.scan && this.scan.status;
    if (!st) return;
    const p = st.progress || {};
    const stats = document.getElementById("sb-stats");
    const cur = document.getElementById("sb-cur");
    if (stats) stats.textContent = `· ${U.num(p.files || 0)} files · ${U.num(p.dirs || 0)} folders · ${U.bytes(p.bytes || 0)} · ${U.duration(st.elapsed || 0)}`;
    if (cur) cur.textContent = p.phase === "finalizing" ? "Crunching the numbers…" : p.phase === "insights" ? "Looking for insights…" : p.current || "";
    const v = Views[this.view];
    if (v && v.onScanProgress) v.onScanProgress(st);
  },
  hideScanBanner() { const b = document.getElementById("scan-banner"); if (b) b.remove(); },
};

window.addEventListener("DOMContentLoaded", () => App.init().catch((err) => {
  console.error(err);
  document.getElementById("view").innerHTML = `<div class="page">${R.empty("alert", "SpaceHound could not start", U.esc(err.message || String(err)))}</div>`;
}));
