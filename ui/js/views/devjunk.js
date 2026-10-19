/* Developer junk: rebuildable artifacts (node_modules, build, .gradle, target…) per project. */

Views.devjunk = {
  title: "Dev junk",
  icon: "code",
  needsScan: true,
  what: "build artifacts in your projects",

  async render(host) {
    const st = (App.state.dev = App.state.dev || { idle: 0, open: {} });
    this.host = host;
    host.innerHTML = `<div class="page">${R.loading("Looking for node_modules, build folders and caches…")}</div>`;
    const res = await API.dev_artifacts({});
    this.res = res;
    this.sel = new Selection(() => this.updateSel());
    this.draw();
  },

  draw() {
    const st = App.state.dev;
    const host = this.host;
    const res = this.res;
    const projects = res.projects.filter((p) => (p.idle_days || 0) >= st.idle);
    const total = projects.reduce((a, p) => a + p.size, 0);
    const kinds = {};
    res.projects.forEach((p) => p.artifacts.forEach((a) => (kinds[a.kind] = (kinds[a.kind] || 0) + a.size)));
    const kindChips = Object.entries(kinds).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<span class="badge accent">${U.esc(k)} · ${U.bytes(v)}</span>`).join(" ");
    const rows = projects.map((p) => {
      const allOn = p.artifacts.every((a) => this.sel.has(a));
      const open = st.open[p.id];
      return `<div class="card dup-group">
        <div class="dup-head" data-proj="${p.id}">
          <input type="checkbox" class="check" data-pck="${p.id}" ${allOn ? "checked" : ""}>
          <div class="dup-thumb" style="width:40px;height:40px;background:var(--accent-soft);color:var(--accent-2)">${icon("code")}</div>
          <div style="flex:1;min-width:0"><div class="ellipsis" style="font-weight:620">${U.esc(p.name)}</div>
            <div class="small muted ellipsis">${U.esc(p.path)}</div></div>
          <div class="small" style="text-align:right;min-width:140px"><div class="${R.ageClass(p.idle_days || 0)}">${p.idle_days == null ? "unknown" : p.idle_days < 1 ? "active today" : "idle " + U.ago(p.last_active).replace(" ago", "")}</div>
            <div class="muted">${p.kinds.map(U.esc).join(", ")}</div></div>
          <div style="text-align:right;min-width:90px;font:650 15px var(--font-display)">${U.bytes(p.size)}</div>
          <button class="btn ghost sm icon" data-open="${p.id}">${icon(open ? "chev-down" : "chev-right", "sm")}</button>
        </div>
        ${open ? `<div class="dup-files">${p.artifacts.map((a) => `<div class="dup-file ${this.sel.has(a) ? "sel" : ""}" data-art="${a.id}">
            <input type="checkbox" class="check" ${this.sel.has(a) ? "checked" : ""}>
            <div class="p"><b>${U.esc(a.name)}</b><span>${U.esc(a.path)}</span></div>
            <div class="small text-2">${U.esc(a.kind)} · ${U.num(a.files)} files</div>
            <div class="row" style="gap:8px"><b class="num">${U.bytes(a.size)}</b><button class="btn ghost sm icon" data-reveal="${U.esc(a.path)}">${icon("folder", "sm")}</button></div>
          </div>`).join("")}</div>` : ""}
      </div>`;
    }).join("");
    host.innerHTML = `<div class="page fade-in">
      <div class="card big-cta" style="margin-bottom:16px">
        <div class="fi" style="width:52px;height:52px;border-radius:14px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent-2)">${icon("code", "lg")}</div>
        <div><div class="amount">${U.bytes(total)}</div><div class="muted small">in ${projects.length} project(s) - all of it is recreated by npm install, gradle build, cargo build…</div></div>
        <div class="spacer"></div>
        <span class="text-2 small">Idle for at least</span>
        <select class="input" id="idle">${[[0, "any time"], [30, "1 month"], [90, "3 months"], [180, "6 months"], [365, "1 year"]].map(([v, l]) => `<option value="${v}" ${st.idle === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        <button class="btn" id="selall">Select all shown</button>
      </div>
      ${kindChips ? `<div class="row wrap" style="margin-bottom:14px">${kindChips}</div>` : ""}
      ${projects.length ? rows : R.empty("check", "No build junk found", st.idle ? "No idle projects with rebuildable folders. Try a shorter idle time." : "No node_modules, build or cache folders over 1 MB inside projects.")}
    </div>`;
    host.querySelector("#idle").onchange = (e) => { st.idle = +e.target.value; this.draw(); };
    host.querySelector("#selall").onclick = () => { projects.forEach((p) => p.artifacts.forEach((a) => this.sel.map.set(a.path, a))); this.sel.changed(); this.draw(); };
    host.querySelectorAll("[data-open]").forEach((b) => (b.onclick = (e) => { e.stopPropagation(); st.open[b.dataset.open] = !st.open[b.dataset.open]; this.draw(); }));
    host.querySelectorAll("[data-pck]").forEach((c) => (c.onclick = (e) => {
      e.stopPropagation();
      const p = res.projects.find((x) => x.id === +c.dataset.pck);
      p.artifacts.forEach((a) => (c.checked ? this.sel.map.set(a.path, a) : this.sel.map.delete(a.path)));
      this.sel.changed();
      this.draw();
    }));
    host.querySelectorAll("[data-proj]").forEach((h) => (h.onclick = (e) => {
      if (e.target.closest("input,button")) return;
      st.open[h.dataset.proj] = !st.open[h.dataset.proj];
      this.draw();
    }));
    host.querySelectorAll("[data-art]").forEach((r) => (r.onclick = (e) => {
      const rv = e.target.closest("[data-reveal]");
      if (rv) { Actions.reveal(rv.dataset.reveal); return; }
      const a = res.projects.flatMap((p) => p.artifacts).find((x) => x.id === +r.dataset.art);
      this.sel.toggle(a);
      this.draw();
    }));
    this.updateSel();
  },

  updateSel() {
    renderSelBar(this.host, this.sel, [
      { label: "Recycle Bin", icon: "trash", onClick: () => Actions.delete(this.sel.items, { mode: "recycle", source: "devjunk" }) },
      { label: "Delete permanently", icon: "trash-x", kind: "danger", onClick: () => Actions.delete(this.sel.items, { mode: "permanent", source: "devjunk" }) },
    ]);
  },
};

/* ======================================================================= */

Views.empty = {
  title: "Empty folders",
  icon: "folder-x",
  needsScan: true,
  what: "empty folders",

  async render(host) {
    const st = (App.state.empty = App.state.empty || { hidden: false });
    const res = await API.empty({ include_hidden: st.hidden });
    const sel = new Selection(() => renderSelBar(host, sel, [
      { label: "Delete empty folders", icon: "trash-x", kind: "danger", onClick: () => Actions.delete(sel.items, { mode: "permanent", source: "empty" }) },
    ]));
    host.innerHTML = `<div class="page fade-in">
      <div class="toolbar">
        <div class="text-2"><b style="color:var(--text)">${U.num(res.count)}</b> empty folders (only the top-most of each empty branch is listed)</div>
        <div class="spacer"></div>
        <label class="row small text-2" style="gap:8px"><span class="toggle"><input type="checkbox" id="hid" ${st.hidden ? "checked" : ""}><span></span></span>Include hidden & system</label>
        <button class="btn sm" id="all">Select all</button>
      </div>
      <div class="notice info" style="margin-bottom:14px">${icon("info", "sm")}<div class="t">Empty folders take no real space but clutter your drive. Windows, Program Files and AppData are skipped because apps expect their folders to exist.</div></div>
      <div id="list"></div></div>`;
    const items = res.items.map((i) => ({ ...i, type: "dir", size: 0 }));
    FileTable.mount(host.querySelector("#list"), items, sel, { showType: false, emptyTitle: "No empty folders", emptyText: "Everything has something in it." });
    host.querySelector("#hid").onchange = (e) => { st.hidden = e.target.checked; App.render(); };
    host.querySelector("#all").onclick = () => { sel.set(items); host.querySelectorAll("tbody tr").forEach((r) => { r.classList.add("sel"); r.querySelector("[data-ck]").checked = true; }); };
  },
};
