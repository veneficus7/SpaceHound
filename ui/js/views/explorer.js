/* Explorer: drill-down folder browser with size bars and a details panel. */

Views.explorer = {
  title: "Explorer",
  icon: "folder",
  needsScan: true,
  what: "your folders",

  async render(host, params) {
    const st = (App.state.explorer = App.state.explorer || { node: null, sort: "size", desc: true, filter: "" });
    if (params.node != null) { st.node = params.node; params.node = null; }
    const data = await API.children(st.node, st.sort, st.desc);
    st.node = data.node.id;
    this.data = data;
    this.host = host;
    const sel = (this.sel = new Selection(() => renderSelBar(host, sel, selButtons(sel, "explorer"))));
    const n = data.node;
    const crumbs = data.crumbs.map((c, i) => `${i ? `<span class="sep">${icon("chev-right", "sm")}</span>` : ""}<a data-crumb="${c.id}">${U.esc(c.name)}</a>`).join("");
    host.innerHTML = `<div class="page fade-in">
      <div class="toolbar">
        <button class="btn icon" id="up" title="Up one level (Backspace)" ${n.parent == null ? "disabled" : ""}>${icon("arrow-up")}</button>
        <div class="crumbs">${crumbs}</div>
        <div class="spacer"></div>
        <input class="input sm" id="flt" placeholder="Filter this folder…" value="${U.esc(st.filter)}" style="width:200px">
        <select class="input sm" id="sort">
          ${[["size", "Sort by size"], ["name", "Sort by name"], ["files", "Sort by file count"], ["mtime", "Sort by last change"], ["type", "Sort by type"]].map(([k, l]) => `<option value="${k}" ${st.sort === k ? "selected" : ""}>${l}</option>`).join("")}
        </select>
        <button class="btn sm" id="map">${icon("map", "sm")}Map</button>
        <button class="btn sm" id="refresh" title="Rescan this folder">${icon("refresh", "sm")}</button>
        <button class="btn sm" id="reveal" title="Open in File Explorer">${icon("external", "sm")}</button>
      </div>
      <div class="row small text-2" style="margin:-4px 0 12px 2px;gap:16px">
        <span><b class="num" style="color:var(--text)">${U.bytes(n.size)}</b> total</span>
        <span>${U.num(n.files)} files</span><span>${U.num(n.dirs)} folders</span><span>last change ${U.ago(n.mtime)}</span>
        ${n.cloud ? `<span>${icon("cloud", "sm")} ${U.bytes(n.cloud)} online-only</span>` : ""}
        ${n.flags & 64 ? `<span class="warn-t">${icon("lock", "sm")} some subfolders were not readable</span>` : ""}
      </div>
      <div class="split"><div id="list"></div><div class="details" id="details"></div></div>
    </div>`;
    host.querySelector("#up").onclick = () => this.up();
    host.querySelectorAll("[data-crumb]").forEach((a) => (a.onclick = () => App.go("explorer", { node: +a.dataset.crumb })));
    host.querySelector("#sort").onchange = (e) => { st.sort = e.target.value; st.desc = st.sort !== "name"; App.render(); };
    host.querySelector("#map").onclick = () => App.go("map", { node: n.id });
    host.querySelector("#refresh").onclick = () => Actions.refresh(n.id);
    host.querySelector("#reveal").onclick = () => n.path && Actions.open(n.path);
    const flt = host.querySelector("#flt");
    flt.oninput = U.debounce(() => { st.filter = flt.value; this.drawList(); }, 120);
    this.drawList();
    this.showDetails({ type: "dir", ...n, self: true });
  },

  up() {
    const n = this.data && this.data.node;
    if (n && n.parent != null) App.go("explorer", { node: n.parent });
  },

  drawList() {
    const st = App.state.explorer;
    const f = (st.filter || "").toLowerCase();
    const items = this.data.items.filter((i) => !f || i.name.toLowerCase().includes(f));
    const host = this.host.querySelector("#list");
    const parentSize = this.data.node.size || 1;
    const sel = this.sel;
    if (!items.length) { host.innerHTML = R.empty("folder", f ? "No matches" : "Empty folder", f ? "Nothing in this folder matches the filter." : "This folder has no files."); return; }
    const rows = items.map((it, i) => {
      const isDir = it.type === "dir", isSmall = it.type === "small";
      const ic = isDir ? R.dirIcon() : isSmall ? `<div class="ico small">${icon("layers")}</div>` : R.fileIcon(it.cat);
      const link = it.flags & 2;
      const meta = isDir ? `${U.num(it.files)} files${it.flags & 1 ? " · not readable" : ""}${link ? " · link (not followed)" : ""}` : isSmall ? "click to list them" : App.catLabel(it.cat);
      return `<tr data-i="${i}" class="${isSmall ? "clickable" : ""} ${!isSmall && sel.has(it) ? "sel" : ""}">
        <td class="w-check">${isSmall ? "" : `<input type="checkbox" class="check" data-ck ${sel.has(it) ? "checked" : ""}>`}</td>
        <td><div class="name-cell">${ic}<div class="txt"><div class="nm">${U.esc(it.name)}</div><div class="muted small ellipsis">${U.esc(meta)}</div></div></div></td>
        <td><div class="size-cell">${R.sizeBar(it.size / parentSize, isDir ? null : isSmall ? "var(--text-3)" : (App.cats[it.cat] || {}).color)}</div></td>
        <td class="r num"><b>${U.bytes(it.size)}</b></td>
        <td class="r num text-2">${U.pct(it.size / parentSize)}</td>
        <td class="text-2" title="${U.esc(U.dateTime(it.mtime))}">${it.mtime ? U.ago(it.mtime) : ""}</td>
        <td>${isSmall ? "" : `<div class="row-actions"><button class="btn ghost sm icon" data-act="menu">${icon("more", "sm")}</button></div>`}</td></tr>`;
    }).join("");
    host.innerHTML = `<div class="card table-wrap"><table class="t">
      <colgroup><col style="width:44px"><col><col style="width:22%"><col style="width:92px"><col style="width:70px"><col style="width:110px"><col style="width:52px"></colgroup>
      <thead><tr><th class="w-check"></th><th>Name</th><th>Share</th><th class="r">Size</th><th class="r">%</th><th>Modified</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
    const itemAt = (tr) => {
      const it = items[+tr.dataset.i];
      if (it.type === "dir" && !it.path) it.path = this.childPath(it.name);
      return it;
    };
    host.onclick = async (e) => {
      const tr = e.target.closest("tr[data-i]");
      if (!tr) return;
      const it = itemAt(tr);
      if (it.type === "small") { this.expandSmall(); return; }
      if (e.target.closest("[data-act]")) { Actions.itemMenu(e, it); return; }
      if (e.target.matches("[data-ck]")) { sel.toggle(it, e.target.checked); tr.classList.toggle("sel", e.target.checked); return; }
      if (it.type === "dir" && !(it.flags & 2)) { App.go("explorer", { node: it.id }); return; }
      host.querySelectorAll("tr.focus").forEach((x) => x.classList.remove("focus"));
      this.showDetails(it);
    };
    host.ondblclick = (e) => {
      const tr = e.target.closest("tr[data-i]");
      if (!tr) return;
      const it = itemAt(tr);
      if (it.type === "file") Actions.open(it.path);
    };
    host.oncontextmenu = (e) => {
      const tr = e.target.closest("tr[data-i]");
      if (!tr) return;
      const it = itemAt(tr);
      if (it.type !== "small") { this.showDetails(it); Actions.itemMenu(e, it); }
    };
    host.onmouseover = U.debounce((e) => {
      const tr = e.target.closest && e.target.closest("tr[data-i]");
      if (!tr) return;
      const it = items[+tr.dataset.i];
      if (it && it.type === "dir") this.showDetails({ ...it, path: this.childPath(it.name) }, true);
    }, 350);
  },

  childPath(name) {
    const base = this.data.node.path || "";
    return base.endsWith("\\") ? base + name : base + "\\" + name;
  },

  async expandSmall() {
    const files = await API.small_files(this.data.node.id);
    const idx = this.data.items.findIndex((i) => i.type === "small");
    if (idx >= 0) this.data.items.splice(idx, 1, ...files);
    this.drawList();
  },

  async showDetails(it, quick) {
    const box = this.host && this.host.querySelector("#details");
    if (!box) return;
    this._detailToken = (this._detailToken || 0) + 1;
    const token = this._detailToken;
    if (it.type === "file") {
      const c = App.cats[it.cat] || App.cats.other;
      box.innerHTML = `<div class="card fade-in"><div class="card-head"><h3>${icon(CAT_ICONS[it.cat] || "file", "sm")}<span class="ellipsis">${U.esc(it.name)}</span></h3></div>
        <div class="card-body">
          <div style="font:650 26px var(--font-display)">${U.bytes(it.size)}</div>
          <dl class="kv"><dt>Type</dt><dd>${R.catBadge(it.cat)}</dd><dt>Modified</dt><dd>${U.dateTime(it.mtime)}<div class="muted small">${U.ago(it.mtime)}</div></dd>
            <dt>Location</dt><dd class="selectable small">${U.esc(it.path)}</dd></dl>
          ${it.cat === "image" ? `<div id="pv" style="border-radius:10px;overflow:hidden;background:var(--surface-2);min-height:40px"></div>` : ""}
          <div class="btn-group"><button class="btn sm" data-a="open">${icon("external", "sm")}Open</button><button class="btn sm" data-a="reveal">${icon("folder", "sm")}Show</button>
            <button class="btn sm" data-a="copy">${icon("copy", "sm")}Copy path</button></div>
          <div class="btn-group"><button class="btn sm" data-a="move">${icon("move", "sm")}Move…</button><button class="btn sm danger-ghost" data-a="del">${icon("trash", "sm")}Delete</button></div>
        </div></div>`;
      this.bindDetailButtons(box, it);
      if (it.cat === "image") API.image_preview(it.path).then((src) => {
        const pv = box.querySelector("#pv");
        if (!src || !pv || token !== this._detailToken) { if (pv) pv.remove(); return; }
        const img = new Image();
        img.style.cssText = "width:100%;display:block";
        img.onload = () => pv.append(img);
        img.onerror = () => pv.remove();
        img.src = src;
      });
      return;
    }
    if (it.type !== "dir") return;
    const d = await API.node_details(it.id);
    if (!d || token !== this._detailToken) return;
    const segs = d.breakdown.slice(0, 8).map((c) => ({ label: c.label, value: c.size, color: c.color, key: c.key }));
    const leg = d.breakdown.slice(0, 6).map((c) => `<div class="dl"><i style="background:${c.color}"></i><span class="ellipsis">${U.esc(c.label)}</span><b>${U.bytes(c.size)}</b><span>${U.pct(c.size / (d.size || 1), 0)}</span></div>`).join("");
    const top = d.top_files.slice(0, 5).map((f) => `<div class="lb" data-reveal="${U.esc(f.path)}"><div class="n"><b>${U.esc(f.name)}</b><span>${U.esc(f.folder)}</span></div><div class="s">${U.bytes(f.size)}</div></div>`).join("");
    const safe = d.safety && d.safety[0];
    box.innerHTML = `<div class="card fade-in"><div class="card-head"><h3>${icon("folder", "sm")}<span class="ellipsis">${U.esc(d.name)}</span></h3>${it.self ? `<span class="badge">This folder</span>` : ""}</div>
      <div class="card-body">
        <div style="display:grid;justify-items:center;gap:10px">${Charts.donut(segs, { size: 132, thickness: 16, center: U.bytes(d.size), sub: "" })}<div class="donut-legend" style="width:100%">${leg}</div></div>
        <dl class="kv"><dt>Files</dt><dd>${U.num(d.files)}</dd><dt>Folders</dt><dd>${U.num(d.dirs)}</dd><dt>Last change</dt><dd>${U.ago(d.mtime)}</dd>
          <dt>Location</dt><dd class="selectable small">${U.esc(d.path)}</dd></dl>
        ${top ? `<div><div class="muted small" style="margin-bottom:4px">Largest files inside</div><div class="list-bars">${top}</div></div>` : ""}
        ${safe === "blocked" ? `<div class="notice info">${icon("shield", "sm")}<div class="t">${U.esc(d.safety[1])}</div></div>` : ""}
        <div class="btn-group"><button class="btn sm" data-a="explore">${icon("folder-open", "sm")}Open</button><button class="btn sm" data-a="map">${icon("map", "sm")}Map</button>
          <button class="btn sm" data-a="dups">${icon("files", "sm")}Duplicates</button><button class="btn sm" data-a="reveal">${icon("external", "sm")}Explorer</button></div>
        ${safe !== "blocked" ? `<div class="btn-group"><button class="btn sm" data-a="move">${icon("move", "sm")}Move…</button><button class="btn sm danger-ghost" data-a="del">${icon("trash", "sm")}Delete folder</button></div>` : ""}
      </div></div>`;
    this.bindDetailButtons(box, { ...it, path: d.path, size: d.size, id: d.id, type: "dir" });
  },

  bindDetailButtons(box, it) {
    box.querySelectorAll("[data-reveal]").forEach((el) => (el.onclick = () => Actions.reveal(el.dataset.reveal)));
    box.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => {
      const a = b.dataset.a;
      if (a === "open") Actions.open(it.path);
      if (a === "reveal") it.type === "dir" ? Actions.open(it.path) : Actions.reveal(it.path);
      if (a === "copy") Actions.copy(it.path);
      if (a === "move") Actions.move([it]);
      if (a === "del") Actions.delete([it]);
      if (a === "explore") App.go("explorer", { node: it.id });
      if (a === "map") App.go("map", { node: it.id });
      if (a === "dups") App.go("duplicates", { roots: [it.path] });
    }));
  },
};
