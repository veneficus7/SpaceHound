/* Largest files with filters (type, size, age, name, folder). */

Views.largest = {
  title: "Largest files",
  icon: "files",
  needsScan: true,
  what: "your largest files",

  async render(host, params) {
    const st = (App.state.largest = App.state.largest || { q: "", cats: [], exts: [], min: 0, age: "", node: null, nodeName: "", limit: 300 });
    if (params.cats) { st.cats = params.cats.slice(); st.exts = []; }
    if (params.exts) { st.exts = params.exts.slice(); st.cats = []; }
    if (params.node != null) { st.node = params.node; st.nodeName = ""; }
    if (params.cats || params.exts || params.node != null) { params.cats = params.exts = undefined; params.node = null; }
    this.host = host;
    host.innerHTML = `<div class="page fade-in">
      <div class="card pad" style="display:grid;gap:12px;margin-bottom:14px">
        <div class="row wrap">
          <div class="search-box" style="width:300px">${icon("search", "sm")}<input id="q" placeholder="Name contains… (or *.mp4)" value="${U.esc(st.q)}"></div>
          <select class="input" id="min">
            ${[[0, "Any size"], [10 << 20, "≥ 10 MB"], [100 << 20, "≥ 100 MB"], [500 << 20, "≥ 500 MB"], [1 << 30, "≥ 1 GB"], [5 * (1 << 30), "≥ 5 GB"]].map(([v, l]) => `<option value="${v}" ${+st.min === v ? "selected" : ""}>${l}</option>`).join("")}
          </select>
          <select class="input" id="age">
            ${[["", "Any date"], ["n7", "Changed in last 7 days"], ["n30", "Changed in last 30 days"], ["o180", "Untouched 6+ months"], ["o365", "Untouched 1+ year"], ["o730", "Untouched 2+ years"], ["o1825", "Untouched 5+ years"]].map(([v, l]) => `<option value="${v}" ${st.age === v ? "selected" : ""}>${l}</option>`).join("")}
          </select>
          ${st.node != null ? `<span class="chip on" id="scope">${icon("folder", "sm")}<span id="scopeName">in folder</span><span class="x">${icon("x", "sm")}</span></span>` : ""}
          ${st.exts.length ? `<span class="chip on" id="extchip">.${U.esc(st.exts.join(", ."))}<span class="x">${icon("x", "sm")}</span></span>` : ""}
          <div class="spacer"></div>
          <button class="btn sm" id="export">${icon("download", "sm")}Export CSV</button>
        </div>
        <div class="chips" id="cats">${App.catList.map((c) => `<span class="chip ${st.cats.includes(c.key) ? "on" : ""}" data-cat="${c.key}"><span class="dot" style="background:${c.color}"></span>${U.esc(c.label)}</span>`).join("")}</div>
      </div>
      <div class="row small text-2" id="summary" style="margin:0 2px 10px"></div>
      <div id="table">${R.loading("Finding the biggest files…")}</div>
      <div style="text-align:center;margin-top:14px" id="more"></div>
    </div>`;
    const reload = () => this.load();
    const q = host.querySelector("#q");
    q.oninput = U.debounce(() => { st.q = q.value; st.limit = 300; reload(); }, 250);
    host.querySelector("#min").onchange = (e) => { st.min = +e.target.value; st.limit = 300; reload(); };
    host.querySelector("#age").onchange = (e) => { st.age = e.target.value; st.limit = 300; reload(); };
    host.querySelectorAll("[data-cat]").forEach((c) => (c.onclick = () => {
      const k = c.dataset.cat;
      st.cats = st.cats.includes(k) ? st.cats.filter((x) => x !== k) : [...st.cats, k];
      c.classList.toggle("on");
      st.limit = 300;
      reload();
    }));
    const scope = host.querySelector("#scope");
    if (scope) {
      scope.onclick = () => { st.node = null; App.render(); };
      API.node_details(st.node).then((d) => { const el = host.querySelector("#scopeName"); if (d && el) el.textContent = `in ${d.name}`; });
    }
    const extchip = host.querySelector("#extchip");
    if (extchip) extchip.onclick = () => { st.exts = []; App.render(); };
    host.querySelector("#export").onclick = async () => {
      const p = await API.export("largest", this.opts());
      if (p) UI.toast(`Saved ${U.esc(p)}`, "good");
    };
    await this.load();
  },

  opts() {
    const st = App.state.largest;
    const o = { query: st.q, cats: st.cats, exts: st.exts, min_size: st.min, limit: st.limit, node_id: st.node };
    if (st.age.startsWith("n")) o.newer_days = +st.age.slice(1);
    if (st.age.startsWith("o")) o.older_days = +st.age.slice(1);
    return o;
  },

  async load() {
    const st = App.state.largest;
    const res = await API.largest(this.opts());
    const host = this.host;
    if (!host.querySelector("#table")) return;
    host.querySelector("#summary").innerHTML = `<span><b style="color:var(--text)">${U.num(res.matched)}</b> files match · <b style="color:var(--text)">${U.bytes(res.matched_size)}</b></span>
      <span class="muted">Only files ≥ ${U.bytes(res.threshold)} are listed individually.</span>`;
    const sel = new Selection(() => renderSelBar(host, sel, selButtons(sel, "largest")));
    FileTable.mount(host.querySelector("#table"), res.items, sel, { emptyTitle: "No files match", emptyText: "Try different filters." });
    const more = host.querySelector("#more");
    more.innerHTML = res.items.length < res.matched && st.limit < 5000 ? `<button class="btn">${icon("chev-down", "sm")}Show more</button>` : "";
    if (more.firstChild) more.firstChild.onclick = () => { st.limit = Math.min(5000, st.limit + 500); this.load(); };
  },
};

/* ======================================================================= */

Views.types = {
  title: "File types",
  icon: "pie",
  needsScan: true,
  what: "file types",

  async render(host) {
    const res = await API.types(null);
    const total = res.categories.reduce((a, c) => a + c.size, 0) || 1;
    const cards = res.categories.map((c) => `<div class="card feature" data-cat="${c.key}" style="flex-direction:column;gap:10px">
        <div class="row"><div class="fi" style="background:${U.hexToRgba(c.color, 0.15)};color:${c.color}">${icon(CAT_ICONS[c.key] || "file")}</div>
          <div style="min-width:0"><h4>${U.esc(c.label)}</h4><p>${U.num(c.count)} files</p></div><div class="spacer"></div>
          <div style="text-align:right"><div style="font:650 18px var(--font-display)">${U.bytes(c.size)}</div><div class="muted small">${U.pct(c.size / total)}</div></div></div>
        ${R.sizeBar(c.size / res.categories[0].size, c.color)}</div>`).join("");
    host.innerHTML = `<div class="page fade-in">
      <div class="card pad" style="margin-bottom:16px">${Charts.stackbar(res.categories.map((c) => ({ label: c.label, value: c.size, color: c.color })), total)}</div>
      <div class="grid g3">${cards}</div>
      <h2 class="section">${icon("tag")}By extension <span class="sub">${U.num(res.ext_count)} different extensions</span>
        <div class="spacer"></div><input class="input sm" id="ef" placeholder="Filter extensions…" style="width:200px">
        <button class="btn sm" id="export">${icon("download", "sm")}Export CSV</button></h2>
      <div id="exts"></div></div>`;
    host.querySelectorAll("[data-cat]").forEach((c) => (c.onclick = () => App.go("largest", { cats: [c.dataset.cat] })));
    host.querySelector("#export").onclick = async () => { const p = await API.export("types"); if (p) UI.toast(`Saved ${U.esc(p)}`, "good"); };
    const maxExt = Math.max(1, ...res.exts.map((e) => e.size));
    const draw = (f) => {
      const rows = res.exts.filter((e) => !f || e.ext.includes(f)).slice(0, 300).map((e) => {
        const c = App.cats[e.cat] || App.cats.other;
        return `<tr class="clickable" data-ext="${U.esc(e.ext)}"><td><b>.${U.esc(e.ext)}</b></td><td>${R.catBadge(e.cat)}</td>
          <td class="r num">${U.num(e.count)}</td><td class="r num">${U.bytes(e.size / Math.max(1, e.count))}</td>
          <td><div class="size-cell">${R.sizeBar(e.size / maxExt, c.color)}<b class="num" style="width:74px;text-align:right">${U.bytes(e.size)}</b></div></td></tr>`;
      }).join("");
      host.querySelector("#exts").innerHTML = `<div class="card table-wrap"><table class="t"><colgroup><col style="width:160px"><col style="width:170px"><col style="width:110px"><col style="width:110px"><col></colgroup>
        <thead><tr><th>Extension</th><th>Category</th><th class="r">Files</th><th class="r">Average</th><th>Total</th></tr></thead><tbody>${rows}</tbody></table></div>`;
      host.querySelectorAll("[data-ext]").forEach((r) => (r.onclick = () => {
        const ext = r.dataset.ext;
        if (ext.startsWith("(")) return;
        App.go("largest", { exts: [ext] });
      }));
    };
    const ef = host.querySelector("#ef");
    ef.oninput = U.debounce(() => draw(ef.value.trim().toLowerCase().replace(/^\./, "")), 120);
    draw("");
  },
};
