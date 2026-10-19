/* Old & forgotten: big files nobody touched, and whole folders that went stale. */

Views.old = {
  title: "Old & forgotten",
  icon: "clock",
  needsScan: true,
  what: "old and forgotten files",

  async render(host) {
    const st = (App.state.old = App.state.old || { tab: "folders", days: 365, min: 100 << 20, fmin: 500 << 20, system: false });
    const s = App.summary;
    const age = Charts.columns(s.age.map((a, i) => ({ label: a.label, value: a.size, sub: `${U.num(a.count)} files`,
      color: ["#aaeefa", "#6cc2ae", "#e9c46a", "#f0a93c", "#e0603c", "#a8452b"][i] })), { height: 150 });
    host.innerHTML = `<div class="page fade-in">
      <div class="card"><div class="card-head"><h3>${icon("clock", "sm")}Space by last modification</h3><span class="sub">How much of your data is actually in use?</span></div>
        <div class="card-body">${age}</div></div>
      <div class="tabs" style="margin-top:18px">
        <button data-tab="folders" class="${st.tab === "folders" ? "on" : ""}">${icon("folder", "sm")}Forgotten folders</button>
        <button data-tab="files" class="${st.tab === "files" ? "on" : ""}">${icon("file", "sm")}Old files</button>
      </div>
      <div class="row wrap" style="margin-bottom:12px">
        <span class="text-2">Not modified for</span>
        <select class="input sm" id="days">${[[90, "3 months"], [180, "6 months"], [365, "1 year"], [730, "2 years"], [1095, "3 years"], [1825, "5 years"]].map(([v, l]) => `<option value="${v}" ${st.days === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        <span class="text-2">and at least</span>
        <select class="input sm" id="min">${[[10 << 20, "10 MB"], [100 << 20, "100 MB"], [500 << 20, "500 MB"], [1 << 30, "1 GB"], [5 * (1 << 30), "5 GB"]].map(([v, l]) => `<option value="${v}" ${(st.tab === "files" ? st.min : st.fmin) === v ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${st.tab === "folders" ? `<label class="row small text-2" style="gap:8px;margin-left:8px"><span class="toggle"><input type="checkbox" id="sys" ${st.system ? "checked" : ""}><span></span></span>Include system & app folders</label>` : ""}
        <div class="spacer"></div><span class="small text-2" id="sum"></span>
      </div>
      <div id="list">${R.loading()}</div></div>`;
    host.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { st.tab = b.dataset.tab; App.render(); }));
    host.querySelector("#days").onchange = (e) => { st.days = +e.target.value; this.load(); };
    host.querySelector("#min").onchange = (e) => { if (st.tab === "files") st.min = +e.target.value; else st.fmin = +e.target.value; this.load(); };
    const sys = host.querySelector("#sys");
    if (sys) sys.onchange = () => { st.system = sys.checked; this.load(); };
    this.host = host;
    await this.load();
  },

  async load() {
    const st = App.state.old;
    const host = this.host;
    const list = host.querySelector("#list");
    const sel = new Selection(() => renderSelBar(host, sel, selButtons(sel, "old")));
    if (st.tab === "files") {
      const res = await API.largest({ older_days: st.days, min_size: st.min, limit: 1000 });
      host.querySelector("#sum").innerHTML = `<b>${U.num(res.matched)}</b> files · <b>${U.bytes(res.matched_size)}</b>`;
      FileTable.mount(list, res.items, sel, { emptyTitle: "No old files", emptyText: "Nothing that big has been sitting untouched that long." });
    } else {
      const res = await API.stale({ days: st.days, min_size: st.fmin, include_system: st.system });
      host.querySelector("#sum").innerHTML = `<b>${U.num(res.items.length)}</b> folders · <b>${U.bytes(res.total)}</b>`;
      FileTable.mount(list, res.items, sel, {
        showType: false, emptyTitle: "No forgotten folders", emptyText: "Every big folder has been touched recently.",
        extraCol: { label: "Idle", width: 120, render: (it) => `<span class="${R.ageClass(it.idle_days)}">${U.ago(it.mtime).replace(" ago", "")}</span>`, sortValue: (it) => it.idle_days },
      });
    }
  },
};
