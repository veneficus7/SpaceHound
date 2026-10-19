/* History (snapshots & growth), Apps, Activity, Settings and Search. */

Views.history = {
  title: "History",
  icon: "history",
  needsScan: true,
  what: "how your disk changed",

  async render(host, params) {
    const st = (App.state.history = App.state.history || { compare: null });
    const snaps = await API.snapshots(false);
    const s = App.summary;
    const current = snaps.find((x) => Math.abs(x.time - s.finished) < 120);
    const older = snaps.filter((x) => x !== current && x.time < s.finished - 60);
    if (!st.compare || !older.some((o) => o.id === st.compare)) st.compare = older.length ? older[0].id : null;
    const points = snaps.slice().reverse().map((x) => ({ t: x.time, v: x.total }));
    host.innerHTML = `<div class="page fade-in">
      <div class="card"><div class="card-head"><h3>${icon("trend", "sm")}Scanned size over time</h3><span class="sub">${U.esc(s.roots.join(", "))} · ${snaps.length} snapshot(s)</span></div>
        <div class="card-body">${Charts.area(points)}</div></div>
      ${older.length ? `<div class="toolbar" style="margin-top:18px">
          <b>Compare this scan with</b>
          <select class="input" id="cmp">${older.map((o) => `<option value="${o.id}" ${o.id === st.compare ? "selected" : ""}>${U.dateTime(o.time)} · ${U.bytes(o.total)}</option>`).join("")}</select>
          <div class="spacer"></div><button class="btn sm" id="delsnap">${icon("trash", "sm")}Delete that snapshot</button></div>
        <div id="diff">${R.loading("Comparing…")}</div>`
      : `<div style="margin-top:16px">${R.empty("history", "Your first snapshot is saved", "SpaceHound remembers folder sizes after every scan. Scan again in a few days and this page shows exactly which folders grew - the easiest way to catch what is filling your disk.")}</div>`}
    </div>`;
    if (!older.length) return;
    host.querySelector("#cmp").onchange = (e) => { st.compare = e.target.value; App.render(); };
    host.querySelector("#delsnap").onclick = async () => {
      if (!(await UI.confirm({ title: "Delete snapshot?", message: "Only the remembered sizes are removed - no files are touched.", confirmLabel: "Delete", danger: true }))) return;
      await API.delete_snapshot(st.compare);
      st.compare = null;
      App.render();
    };
    const d = await API.compare_snapshot(st.compare);
    const max = Math.max(1, ...[...d.grew, ...d.shrank].map((c) => Math.abs(c.delta)));
    const table = (list, grow) => list.length ? `<div class="card table-wrap"><table class="t"><colgroup><col><col style="width:110px"><col style="width:110px"><col style="width:230px"></colgroup>
      <thead><tr><th>Folder</th><th class="r">Before</th><th class="r">Now</th><th>Change</th></tr></thead><tbody>
      ${list.map((c) => `<tr class="clickable" data-path="${U.esc(c.path)}"><td><div class="name-cell">${R.dirIcon()}<div class="txt"><div class="nm">${U.esc(U.basename(c.path))}
          ${c.is_new ? `<span class="badge info">new</span>` : ""}${c.is_gone ? `<span class="badge">gone</span>` : ""}</div><div class="pth">‎${U.esc(c.path)}‎</div></div></div></td>
        <td class="r num text-2">${U.bytes(c.old)}</td><td class="r num">${U.bytes(c.new)}</td>
        <td><div class="size-cell">${R.sizeBar(Math.abs(c.delta) / max, grow ? "var(--bad)" : "var(--good)")}<b class="num ${grow ? "bad-t" : "good-t"}" style="width:80px;text-align:right">${grow ? "+" : "−"}${U.bytes(Math.abs(c.delta))}</b></div></td></tr>`).join("")}
      </tbody></table></div>` : `<div class="muted small" style="padding:12px 4px">Nothing significant.</div>`;
    const tone = d.total_delta > 0 ? "bad-t" : "good-t";
    host.querySelector("#diff").innerHTML = `
      <div class="card big-cta"><div><div class="muted small">Since ${U.dateTime(d.snapshot.time)} (${U.ago(d.snapshot.time)})</div>
        <div class="amount ${tone}">${d.total_delta >= 0 ? "+" : "−"}${U.bytes(Math.abs(d.total_delta))}</div></div><div class="spacer"></div>
        <div class="text-2 small" style="max-width:420px">Only the most specific folders are listed: if a change is explained by one subfolder, you see that subfolder instead of all its parents.</div></div>
      <h2 class="section">${icon("trend")}What grew</h2>${table(d.grew, true)}
      <h2 class="section">${icon("trend-down")}What shrank</h2>${table(d.shrank, false)}`;
    host.querySelectorAll("[data-path]").forEach((r) => (r.onclick = async () => {
      const id = await API.find_node(r.dataset.path);
      if (id != null) App.go("explorer", { node: id }); else UI.toast("That folder no longer exists", "info");
    }));
  },
};

/* ======================================================================= */

Views.apps = {
  title: "Installed apps",
  icon: "package",

  async render(host) {
    const st = (App.state.apps = App.state.apps || { data: null, q: "", sort: "size" });
    this.host = host;
    if (!st.data) {
      const id = await API.start_apps();
      try {
        st.data = await inlineJob(host, id, { title: "Measuring installed apps", describe: (p) => `${U.esc(p.current || "")} <span class="muted">(${p.done || 0}/${p.total || "…"})</span>` });
      } catch (err) {
        host.innerHTML = `<div class="page">${R.empty("alert", "Could not list apps", U.esc(err.message))}</div>`;
        return;
      }
    }
    this.draw();
  },

  draw() {
    const st = App.state.apps;
    const host = this.host;
    const q = st.q.toLowerCase();
    let apps = st.data.apps.filter((a) => !q || a.name.toLowerCase().includes(q) || (a.publisher || "").toLowerCase().includes(q));
    if (st.sort === "name") apps = apps.slice().sort((a, b) => a.name.localeCompare(b.name));
    if (st.sort === "date") apps = apps.slice().sort((a, b) => (b.installed || "").localeCompare(a.installed || ""));
    const max = Math.max(1, ...apps.map((a) => a.size || 0));
    const fmtDate = (d) => (d && d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : "—");
    // same product installed in several versions side by side (e.g. "Premiere Pro 2025" + "2026")
    const older = new Set();
    const families = {};
    // runtimes & SDKs are often needed side by side by other programs - never suggest removing those
    const runtime = /redistributable|runtime|\bsdk\b|driver|framework|\.net|visual c\+\+|webview|directx|python|java|jdk|jre|node\.?js|windows kit|update|launcher|toolkit/i;
    st.data.apps.forEach((a) => {
      if (runtime.test(a.name)) return;
      const m = a.name.match(/^(.*?)[\s_-]+v?(\d{4}|\d+(?:\.\d+)+)(?:\.\d+)*\s*(?:\(.*\))?$/i);
      if (m) (families[m[1].toLowerCase().trim()] = families[m[1].toLowerCase().trim()] || []).push({ a, v: m[2] });
    });
    const cmpVer = (x, y) => { const p = x.split("."), q = y.split("."); for (let i = 0; i < Math.max(p.length, q.length); i++) { const d = (+p[i] || 0) - (+q[i] || 0); if (d) return d; } return 0; };
    Object.values(families).forEach((list) => {
      if (list.length < 2) return;
      list.sort((x, y) => cmpVer(y.v, x.v));
      list.slice(1).forEach((x) => { if (x.v !== list[0].v) older.add(x.a); });
    });
    const olderList = st.data.apps.filter((a) => older.has(a));
    const olderSize = olderList.reduce((s, a) => s + (a.shared ? 0 : a.size || 0), 0);
    host.innerHTML = `<div class="page fade-in">
      <div class="toolbar">
        <div class="search-box" style="width:300px">${icon("search", "sm")}<input id="q" placeholder="Search apps…" value="${U.esc(st.q)}"></div>
        <select class="input sm" id="sort">${[["size", "Largest first"], ["name", "Name"], ["date", "Recently installed"]].map(([k, l]) => `<option value="${k}" ${st.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select>
        <span class="text-2 small">${apps.length} apps${q ? "" : ` · ${U.bytes(st.data.total)}`}</span>
        <div class="spacer"></div>
        <button class="btn sm" id="export">${icon("download", "sm")}Export</button>
        <button class="btn sm" id="reload">${icon("refresh", "sm")}Re-measure</button>
        <button class="btn sm" id="settings">${icon("external", "sm")}Windows Apps settings</button>
      </div>
      ${olderList.length ? `<div class="notice warn" style="margin-bottom:14px">${icon("layers", "sm")}<div><b>Older versions installed side by side${olderSize ? ` · ${U.bytes(olderSize)}` : ""}</b>
        <div class="t">${olderList.map((a) => U.esc(a.name)).join(", ")}. If you only use the newest version, uninstalling the old ones frees this space.</div></div></div>` : ""}
      <div class="card table-wrap"><table class="t"><colgroup><col><col style="width:120px"><col style="width:110px"><col style="width:240px"><col style="width:150px"></colgroup>
        <thead><tr><th>App</th><th>Version</th><th>Installed</th><th>Size</th><th></th></tr></thead><tbody>
        ${apps.map((a, i) => `<tr data-i="${i}"><td><div class="name-cell"><div class="ico dir">${icon("package")}</div><div class="txt"><div class="nm">${U.esc(a.name)}${older.has(a) ? ` <span class="badge warn">older version</span>` : ""}</div>
            <div class="muted small ellipsis">${U.esc(a.publisher || "")}${a.location ? " · " + U.esc(a.location) : ""}</div></div></div></td>
          <td class="text-2 ellipsis">${U.esc(a.version || "")}</td><td class="text-2">${fmtDate(a.installed)}</td>
          <td><div class="size-cell">${R.sizeBar((a.size || 0) / max)}<b class="num" style="width:74px;text-align:right" title="${a.source === "registry" ? "Estimate reported by the installer" : "Measured on disk"}">${a.size ? U.bytes(a.size) : "—"}</b>
            ${a.source === "registry" ? `<span class="badge" title="Estimate from the installer">est.</span>` : ""}
            ${a.shared ? `<span class="badge warn" title="Several apps are installed in this folder - the size covers all of them">shared</span>` : ""}</div></td>
          <td><div class="row" style="gap:4px;justify-content:flex-end">${a.location ? `<button class="btn ghost sm icon" data-loc="${i}" title="Open install folder">${icon("folder", "sm")}</button>` : ""}
            ${a.can_uninstall ? `<button class="btn sm danger-ghost" data-un="${i}">Uninstall</button>` : ""}</div></td></tr>`).join("")}
        </tbody></table></div></div>`;
    const qi = host.querySelector("#q");
    qi.oninput = U.debounce(() => { st.q = qi.value; this.draw(); host.querySelector("#q").focus(); const el = host.querySelector("#q"); el.setSelectionRange(el.value.length, el.value.length); }, 200);
    host.querySelector("#sort").onchange = (e) => { st.sort = e.target.value; this.draw(); };
    host.querySelector("#reload").onclick = () => { st.data = null; this.render(host); };
    host.querySelector("#settings").onclick = () => API.open_external("ms-settings:appsfeatures");
    host.querySelector("#export").onclick = async () => { const p = await API.export("apps"); if (p) UI.toast(`Saved ${U.esc(p)}`, "good"); };
    host.querySelectorAll("[data-loc]").forEach((b) => (b.onclick = () => Actions.open(apps[+b.dataset.loc].location)));
    host.querySelectorAll("[data-un]").forEach((b) => (b.onclick = async () => {
      const a = apps[+b.dataset.un];
      if (!(await UI.confirm({ title: `Uninstall ${a.name}?`, icon: "package", danger: true, message: "SpaceHound starts the app's own uninstaller. Follow its steps to finish.", confirmLabel: "Start uninstaller" }))) return;
      try { await API.uninstall(a.id); UI.toast("Uninstaller started. Click Re-measure when it's done.", "info", 6000); }
      catch (err) { UI.toast(U.esc(err.message), "bad"); }
    }));
  },
};

/* ======================================================================= */

Views.activity = {
  title: "Activity",
  icon: "activity",

  async render(host) {
    const a = await API.activity();
    const labels = { delete: "Deleted", cleanup: "Cleanup", move: "Moved", hardlink: "Hard-linked" };
    const icons = { delete: "trash", cleanup: "sparkles", move: "move", hardlink: "link" };
    const modes = { recycle: `<span class="badge info">Recycle Bin</span>`, permanent: `<span class="badge bad">Permanent</span>`, move: `<span class="badge accent">Move</span>`, hardlink: `<span class="badge good">Hard link</span>` };
    host.innerHTML = `<div class="page fade-in" style="max-width:1000px">
      <div class="card big-cta" style="margin-bottom:16px;background:radial-gradient(600px 200px at 0 0, var(--good-soft), transparent 70%), var(--surface)">
        <div><div class="muted small">Space freed with SpaceHound</div><div class="amount good-t">${U.bytes(a.freed || 0)}</div>
          <div class="muted small">Recycle Bin moves are counted once you empty the bin.</div></div><div class="spacer"></div>
        ${a.entries.length ? `<button class="btn sm" id="clear">${icon("trash", "sm")}Clear history</button>` : ""}</div>
      ${a.entries.length ? `<div class="card">${a.entries.map((e) => `<div class="settings-row" style="grid-template-columns:40px minmax(0,1fr) auto">
          <div class="ico dir" style="width:34px;height:34px;border-radius:9px;display:grid;place-items:center">${icon(icons[e.action] || "activity", "sm")}</div>
          <div style="min-width:0"><h4>${labels[e.action] || e.action} ${e.count ? `${U.num(e.count)} item(s)` : ""} ${modes[e.mode] || ""}</h4>
            <p class="ellipsis">${U.esc((e.items || []).join(", "))}${e.dest ? " → " + U.esc(e.dest) : ""}</p></div>
          <div style="text-align:right"><b class="num">${U.bytes(e.freed)}</b><div class="muted small">${U.dateTime(e.time)}</div></div></div>`).join("")}</div>`
      : R.empty("activity", "No activity yet", "Everything you delete, clean, move or hard-link shows up here.")}
    </div>`;
    const c = host.querySelector("#clear");
    if (c) c.onclick = async () => { await API.clear_activity(); App.render(); };
  },
};

/* ======================================================================= */

Views.settings = {
  title: "Settings",
  icon: "settings",

  installCard(st) {
    if (!st) return "";
    let body;
    if (st.running_installed) {
      body = `<div class="settings-row"><div><h4>${icon("check", "sm")} Installed</h4><p>SpaceHound is in your Start menu - type “SpaceHound” in Windows search to open it.
          <span class="selectable">${U.esc(st.path)}</span></p></div>
        <div class="btn-group">${st.desktop ? "" : `<button class="btn sm" data-inst="desktop">${icon("plus", "sm")}Desktop shortcut</button>`}
          <button class="btn sm danger-ghost" data-inst="uninstall">${icon("trash", "sm")}Uninstall</button></div></div>`;
    } else if (st.can_install && st.installed) {
      body = `<div class="settings-row"><div><h4>Installed copy found</h4><p>You're running a portable copy. Open the installed one, or update it with this version.</p></div>
        <div class="btn-group"><button class="btn sm" data-inst="update">${icon("refresh", "sm")}Update installed copy</button>
          <button class="btn sm primary" data-inst="open">${icon("external", "sm")}Open installed</button></div></div>`;
    } else if (st.can_install) {
      body = `<div class="settings-row"><div><h4>Install SpaceHound</h4><p>Adds SpaceHound to the Start menu and Windows search, and to Apps &amp; features so it can be uninstalled normally. No admin rights needed.</p>
          <label class="row small text-2" style="gap:8px;margin-top:10px"><span class="toggle"><input type="checkbox" id="inst-desk"><span></span></span>Also add a desktop shortcut</label></div>
        <button class="btn primary" data-inst="install">${icon("download", "sm")}Install</button></div>`;
    } else {
      body = `<div class="settings-row"><div><h4>Running from source</h4><p>Build the .exe with <code>build.ps1</code>, then use its Install button (or run <code>SpaceHound.exe --install</code>).</p></div><div></div></div>`;
    }
    return `<h2 class="section">Installation</h2><div class="card">${body}</div>`;
  },

  async render(host) {
    const s = await API.get_settings();
    const info = App.info;
    let inst = null;
    try { inst = await API.install_status(); } catch (_) {}
    const list = (key, items) => `<div class="list-input" data-list="${key}">${items.map((p, i) => `<div class="li"><span>${U.esc(p)}</span><button class="btn ghost sm icon" data-rm="${key}:${i}">${icon("x", "sm")}</button></div>`).join("") || `<div class="muted small">None</div>`}
      <div><button class="btn sm" data-add="${key}">${icon("plus", "sm")}Add folder</button></div></div>`;
    host.innerHTML = `<div class="page fade-in" style="max-width:900px">
      <h2 class="section" style="margin-top:0">Appearance & behaviour</h2>
      <div class="card">
        <div class="settings-row"><div><h4>Theme</h4><p>Dark, light or follow Windows.</p></div>
          <div class="seg" id="theme">${["dark", "light", "system"].map((t) => `<button data-v="${t}" class="${s.theme === t ? "on" : ""}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("")}</div></div>
        <div class="settings-row"><div><h4>Default delete action</h4><p>Used by the Delete buttons. The Recycle Bin lets you undo.</p></div>
          <div class="seg" id="mode">${[["recycle", "Recycle Bin"], ["permanent", "Permanent"]].map(([v, l]) => `<button data-v="${v}" class="${s.delete_mode === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
      </div>
      <h2 class="section">Scanning</h2>
      <div class="card">
        <div class="settings-row"><div><h4>Parallel scan threads</h4><p>More threads finish faster on SSDs. Use 2-4 for spinning hard drives.</p></div>
          <div class="row"><input type="range" min="1" max="32" value="${s.threads}" id="threads"><b id="tv" style="width:24px">${s.threads}</b></div></div>
        <div class="settings-row"><div><h4>Track files individually from</h4><p>Smaller files are summarized per folder to keep memory low. Lower = more detail, more RAM.</p></div>
          <select class="input" id="thr">${[16, 64, 256, 1024].map((v) => `<option value="${v}" ${s.threshold_kb === v ? "selected" : ""}>${v >= 1024 ? v / 1024 + " MB" : v + " KB"}</option>`).join("")}</select></div>
        <div class="settings-row"><div><h4>Snapshots to keep</h4><p>Used by History to show what grew over time.</p></div>
          <select class="input" id="keep">${[10, 30, 100].map((v) => `<option ${s.snapshot_keep === v ? "selected" : ""}>${v}</option>`).join("")}</select></div>
        <div class="settings-row" style="grid-template-columns:1fr"><div><h4>Excluded folders</h4><p>Never scanned (e.g. a huge backup folder or a network drive mount).</p></div>${list("excluded", s.excluded)}</div>
      </div>
      <h2 class="section">Safety</h2>
      <div class="card">
        <div class="settings-row" style="grid-template-columns:1fr"><div><h4>Protected folders</h4><p>SpaceHound refuses to delete or move anything inside these. Windows, Program Files and your main user folders are always protected.</p></div>${list("protected", s.protected)}</div>
      </div>
      ${this.installCard(inst)}
      <h2 class="section">About</h2>
      <div class="card">
        <div class="settings-row"><div><h4>SpaceHound ${U.esc(info.version)}</h4><p>${info.admin ? "Running as administrator." : "Running as a normal user."} Data folder: <span class="selectable">${U.esc(info.data_dir)}</span></p></div>
          <div class="btn-group"><button class="btn sm" id="data">${icon("folder", "sm")}Open data folder</button>
          ${!info.admin && info.platform === "win32" ? `<button class="btn sm" id="adm">${icon("shield", "sm")}Run as administrator</button>` : ""}</div></div>
      </div>
    </div>`;
    const save = async (patch) => { App.settings = await API.save_settings(patch); App.applyTheme(); UI.toast("Saved", "good", 1200); };
    host.querySelectorAll("#theme button").forEach((b) => (b.onclick = async () => { await save({ theme: b.dataset.v }); App.render(); }));
    host.querySelectorAll("#mode button").forEach((b) => (b.onclick = async () => { await save({ delete_mode: b.dataset.v }); App.render(); }));
    const th = host.querySelector("#threads");
    th.oninput = () => (host.querySelector("#tv").textContent = th.value);
    th.onchange = () => save({ threads: +th.value });
    host.querySelector("#thr").onchange = (e) => save({ threshold_kb: +e.target.value });
    host.querySelector("#keep").onchange = (e) => save({ snapshot_keep: +e.target.value });
    host.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = async () => {
      const [key, i] = b.dataset.rm.split(":");
      const arr = s[key].slice(); arr.splice(+i, 1);
      await save({ [key]: arr }); App.render();
    }));
    host.querySelectorAll("[data-add]").forEach((b) => (b.onclick = async () => {
      const key = b.dataset.add;
      const p = App.info.mode === "webview" ? await API.pick_folder() : await UI.prompt({ title: "Add folder", label: "Folder path" });
      if (!p) return;
      await save({ [key]: [...s[key], p] }); App.render();
    }));
    host.querySelector("#data").onclick = () => Actions.open(info.data_dir);
    host.querySelectorAll("[data-inst]").forEach((b) => (b.onclick = () => Installer.run(b.dataset.inst, host)));
    const adm = host.querySelector("#adm");
    if (adm) adm.onclick = () => App.elevate();
  },
};

/* ======================================================================= */

Views.search = {
  title: "Search",
  icon: "search",
  needsScan: true,

  async render(host, params) {
    const q = params.q || "";
    const res = await API.search(q, 500);
    host.innerHTML = `<div class="page fade-in"><div class="row small text-2" style="margin-bottom:12px">
      <span><b style="color:var(--text)">${res.items.length}</b> result(s) for “${U.esc(q)}” (largest first${res.items.length >= 500 ? ", top 500" : ""}). Tip: use wildcards like <code>*.iso</code> or <code>backup*</code>.</span></div>
      <div id="list"></div></div>`;
    const sel = new Selection(() => renderSelBar(host, sel, selButtons(sel, "search")));
    FileTable.mount(host.querySelector("#list"), res.items, sel, { emptyTitle: "No matches", emptyText: "Nothing in the scan matches that name." });
  },
};
