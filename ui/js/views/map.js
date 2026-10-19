/* Visual map: interactive treemap / sunburst of the scan. */

Views.map = {
  title: "Visual map",
  icon: "map",
  needsScan: true,
  what: "the visual map",

  async render(host, params) {
    const st = (App.state.map = App.state.map || { node: null, mode: "treemap", color: "type" });
    if (params.node != null) { st.node = params.node; params.node = null; }
    host.innerHTML = `<div class="page full fade-in"><div class="map-shell">
      <div class="toolbar" style="margin:0">
        <button class="btn icon" id="up" title="Up one level (Backspace)">${icon("arrow-up")}</button>
        <div class="crumbs" id="crumbs"></div>
        <div class="spacer"></div>
        <div class="seg" id="mode">
          <button data-v="treemap" class="${st.mode === "treemap" ? "on" : ""}">${icon("map", "sm")}Treemap</button>
          <button data-v="sunburst" class="${st.mode === "sunburst" ? "on" : ""}">${icon("sunburst", "sm")}Sunburst</button>
          <button data-v="bubbles" class="${st.mode === "bubbles" ? "on" : ""}">${icon("disc", "sm")}Bubbles</button>
        </div>
        <div class="seg" id="color">
          <button data-v="type" class="${st.color === "type" ? "on" : ""}">By type</button>
          <button data-v="age" class="${st.color === "age" ? "on" : ""}">By age</button>
          <button data-v="folder" class="${st.color === "folder" ? "on" : ""}">By folder</button>
        </div>
      </div>
      <div class="map-stage" id="stage"><div class="loading">${R.loading("Drawing the map…")}</div></div>
      <div class="row" style="min-height:30px"><div id="legend" class="legend" style="margin:0;flex:1"></div>
        <div class="muted small" id="maphint">Click a folder to zoom in · right-click for actions · Backspace goes up</div></div>
    </div></div>`;
    const stage = host.querySelector("#stage");
    this.host = host;
    this.map = new SpaceMap(stage, {
      mode: st.mode,
      colorBy: st.color,
      onOpen: (id) => this.load(id),
      onUp: () => this.up(),
      onContext: (e, d) => { if (d.type !== "rest") Actions.itemMenu(e, d); },
      onSelect: (d) => { host.querySelector("#maphint").innerHTML = `${U.esc(d.name)} · <b>${U.bytes(d.size)}</b> · ${U.esc(App.catLabel(d.cat))} — double-click to show in Explorer`; },
      onActivate: (d) => Actions.reveal(d.path),
    });
    host.querySelector("#up").onclick = () => this.up();
    host.querySelectorAll("#mode button").forEach((b) => (b.onclick = () => {
      st.mode = b.dataset.v;
      host.querySelectorAll("#mode button").forEach((x) => x.classList.toggle("on", x === b));
      this.map.setMode(st.mode);
    }));
    host.querySelectorAll("#color button").forEach((b) => (b.onclick = () => {
      st.color = b.dataset.v;
      host.querySelectorAll("#color button").forEach((x) => x.classList.toggle("on", x === b));
      this.map.setColorBy(st.color);
      this.legend();
    }));
    await this.load(st.node);
    return () => { if (this.map) this.map.destroy(); this.map = null; };
  },

  async load(id) {
    const st = App.state.map;
    const res = await API.treemap(id, 12, 6000);
    if (!this.map) return;
    st.node = res.root.i;
    this.res = res;
    const stage = this.host.querySelector("#stage .loading");
    if (stage) stage.remove();
    this.map.setData(res.root, res.path);
    const crumbs = this.host.querySelector("#crumbs");
    crumbs.innerHTML = res.crumbs.map((c, i) => `${i ? `<span class="sep">${icon("chev-right", "sm")}</span>` : ""}<a data-crumb="${c.id}">${U.esc(c.name)}</a>`).join("")
      + `<span class="muted small" style="margin-left:10px">${U.bytes(res.root.s)}</span>`;
    crumbs.querySelectorAll("[data-crumb]").forEach((a) => (a.onclick = () => this.load(+a.dataset.crumb)));
    this.host.querySelector("#up").disabled = res.crumbs.length < 2;
    this.legend();
  },

  up() {
    if (!this.res || this.res.crumbs.length < 2) return;
    this.load(this.res.crumbs[this.res.crumbs.length - 2].id);
  },

  legend() {
    const el = this.host.querySelector("#legend");
    const st = App.state.map;
    if (st.color === "age") {
      el.innerHTML = `<span><i style="background:linear-gradient(90deg,#aaeefa,#6cc2ae,#f0a93c,#e0603c,#7a3a22);width:160px"></i></span>
        <span>new</span><span>→ 1 year</span><span>→ 7 years old</span>`;
    } else if (st.color === "folder") {
      el.innerHTML = `<span class="muted">Each top-level folder gets its own colour.</span>`;
    } else {
      el.innerHTML = App.catList.map((c) => `<span><i style="background:${c.color}"></i>${U.esc(c.label)}</span>`).join("") +
        `<span><i style="background:#4a5262"></i>Small items</span>`;
    }
  },
};
