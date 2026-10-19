/* Smart cleanup: caches, temp files, Recycle Bin, developer caches. */

Views.cleanup = {
  title: "Smart cleanup",
  icon: "sparkles",
  refresh() { /* the view re-analyzes on its own after cleaning */ },

  async render(host, params) {
    const st = (App.state.cleanup = App.state.cleanup || { result: null, selected: null, open: {} });
    this.host = host;
    if (!st.result || params.rescan) {
      params.rescan = false;
      const id = await API.start_cleanup_scan();
      try {
        st.result = await inlineJob(host, id, {
          title: "Measuring caches & junk",
          describe: (p) => `${U.esc(p.current || "")} <span class="muted">(${p.done || 0}/${p.total || "…"})</span>`,
        });
      } catch (err) {
        host.innerHTML = `<div class="page">${R.empty(err.cancelled ? "stop" : "alert", err.cancelled ? "Stopped" : "Could not analyze", U.esc(err.message), `<button class="btn primary" id="again">Try again</button>`)}</div>`;
        host.querySelector("#again").onclick = () => this.render(host, { rescan: true });
        return;
      }
      st.selected = new Set(st.result.items.filter((i) => i.kind !== "info" && i.risk === "safe" && !i.needs_admin && i.size > 0).map((i) => i.id));
    }
    this.draw();
  },

  draw() {
    const st = App.state.cleanup;
    const host = this.host;
    const items = st.result.items;
    const groups = {};
    items.forEach((i) => (groups[i.group] = groups[i.group] || []).push(i));
    const selSize = items.filter((i) => st.selected.has(i.id)).reduce((a, i) => a + i.size, 0);
    const cleanable = items.filter((i) => i.kind !== "info").reduce((a, i) => a + i.size, 0);
    const infoSize = items.filter((i) => i.kind === "info").reduce((a, i) => a + i.size, 0);
    const icons = { Windows: "cpu", Browsers: "eye", Apps: "app", Developer: "code" };
    const groupHtml = Object.entries(groups).map(([g, list]) => `
      <div class="card clean-group"><div class="card-head"><h3>${icon(icons[g] || "sparkles", "sm")}${U.esc(g)}</h3>
        <span class="sub">${U.bytes(list.filter((i) => i.kind !== "info").reduce((a, i) => a + i.size, 0))} cleanable</span></div>
        ${list.map((i) => this.itemHtml(i, st)).join("")}</div>`).join("");
    host.innerHTML = `<div class="page fade-in">
      <div class="card big-cta" style="margin-bottom:18px;background:radial-gradient(600px 200px at 0 0, var(--accent-soft), transparent 70%), var(--surface)">
        <div><div class="muted small">Selected for cleanup</div><div class="amount">${U.bytes(selSize)}</div>
          <div class="muted small">${U.bytes(cleanable)} cleanable in total${infoSize ? ` · ${U.bytes(infoSize)} more explained below` : ""}</div></div>
        <div class="spacer"></div>
        <button class="btn" id="rescan">${icon("refresh", "sm")}Re-analyze</button>
        <button class="btn primary lg" id="clean" ${selSize ? "" : "disabled"}>${icon("sparkles")}Clean selected</button>
      </div>
      <div class="notice info" style="margin-bottom:16px">${icon("info", "sm")}<div class="t">Only well-known caches and temporary files are touched - never your documents, photos or projects.
        Files that are in use are skipped automatically. Close browsers and apps first for the best result.
        ${!App.info.admin ? " Items marked <b>Admin</b> need SpaceHound to run as administrator." : ""}</div></div>
      ${groupHtml || R.empty("check", "Squeaky clean", "No junk found.")}
    </div>`;
    host.querySelector("#rescan").onclick = () => this.render(host, { rescan: true });
    host.querySelector("#clean").onclick = () => this.clean();
    host.querySelectorAll("[data-ck]").forEach((c) => (c.onchange = () => {
      if (c.checked) st.selected.add(c.dataset.ck); else st.selected.delete(c.dataset.ck);
      this.draw();
    }));
    host.querySelectorAll("[data-toggle]").forEach((b) => (b.onclick = () => { st.open[b.dataset.toggle] = !st.open[b.dataset.toggle]; this.draw(); }));
    host.querySelectorAll("[data-reveal]").forEach((b) => (b.onclick = () => Actions.reveal(b.dataset.reveal)));
    host.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = () => Actions.copy(b.dataset.copy)));
    host.querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => API.open_external(b.dataset.open)));
    host.querySelectorAll("[data-explore]").forEach((b) => (b.onclick = async () => {
      if (!App.summary) { Actions.open(b.dataset.explore); return; }
      const id = await API.find_node(b.dataset.explore);
      if (id != null) App.go("explorer", { node: id }); else Actions.open(b.dataset.explore);
    }));
  },

  itemHtml(i, st) {
    const info = i.kind === "info";
    const disabled = info || i.needs_admin || !i.size;
    const risk = info ? `<span class="badge info">Info</span>` : i.risk === "safe" ? `<span class="badge good">Safe</span>` : `<span class="badge warn">Review</span>`;
    const paths = st.open[i.id] ? `<div class="paths">${i.paths.map((p) => `<div><span class="ellipsis" style="flex:1">${U.esc(p.path)}</span><b>${U.bytes(p.size)}</b>
        <button class="btn ghost sm icon" data-reveal="${U.esc(p.path)}" title="Show in Explorer">${icon("folder", "sm")}</button>
        <button class="btn ghost sm icon" data-explore="${U.esc(p.path)}" title="Explore">${icon("search", "sm")}</button></div>`).join("")}</div>` : "";
    return `<div class="clean-item">
      <input type="checkbox" class="check" data-ck="${i.id}" ${st.selected.has(i.id) ? "checked" : ""} ${disabled ? "disabled" : ""}>
      <div style="min-width:0"><div class="nm">${U.esc(i.name)} ${risk}${i.admin ? `<span class="badge ${i.needs_admin ? "bad" : ""}">${icon("shield", "sm")}Admin</span>` : ""}</div>
        <div class="ds">${U.esc(i.desc)}</div>
        ${i.tip ? i.tip.split("|").map((t) => `<div class="tipbox"><code class="selectable">${U.esc(t)}</code><button class="btn ghost sm icon" data-copy="${U.esc(t)}" title="Copy command">${icon("copy", "sm")}</button></div>`).join("") : ""}
        ${i.open ? `<button class="btn sm" style="margin-top:7px" data-open="${U.esc(i.open)}">${icon("external", "sm")}Open Windows settings</button>` : ""}
      </div>
      <div>${i.paths.length ? `<button class="btn ghost sm" data-toggle="${i.id}">${i.kind === "recycle" ? "" : `${i.paths.length} location${i.paths.length > 1 ? "s" : ""}`}${icon(st.open[i.id] ? "chev-down" : "chev-right", "sm")}</button>` : i.kind === "recycle" ? `<span class="muted small">${U.num(i.count)} items</span>` : ""}</div>
      <div class="sz" style="${info ? "color:var(--text-2)" : ""}">${U.bytes(i.size)}<div class="muted small" style="font:400 11.5px var(--font)">${i.kind === "recycle" ? "" : U.num(i.count) + " files"}</div></div>
      ${paths}
    </div>`;
  },

  async clean() {
    const st = App.state.cleanup;
    const chosen = st.result.items.filter((i) => st.selected.has(i.id));
    const total = chosen.reduce((a, i) => a + i.size, 0);
    const review = chosen.filter((i) => i.risk !== "safe");
    const ok = await UI.confirm({
      title: `Clean ${chosen.length} item(s)?`, icon: "sparkles", danger: review.length > 0,
      message: `About <b>${U.bytes(total)}</b> of caches and temporary files will be permanently deleted. Apps recreate them when needed.`,
      details: `<div class="path-list">${chosen.map((i) => `<div><span>${U.esc(i.name)}</span><b>${U.bytes(i.size)}</b></div>`).join("")}</div>
        ${review.length ? `<div class="notice warn">${icon("alert", "sm")}<div class="t"><b>Review:</b> ${review.map((r) => U.esc(r.name)).join(", ")} - these are safe to delete but get re-downloaded or rebuilt (e.g. the next Gradle build is slower).</div></div>` : ""}`,
      confirmLabel: "Clean now",
    });
    if (!ok) return;
    const id = await API.start_cleanup(chosen.map((i) => i.id));
    const res = await UI.runJob(id, { title: "Cleaning up", icon: "sparkles", describe: (p) => `${U.esc(p.current || "")} · freed ${U.bytes(p.freed || 0)}` });
    if (!res) return;
    if (res.freed > 0) FX.confetti();
    const failed = res.results.filter((r) => r.errors);
    await UI.modal({
      title: `Freed ${U.bytes(res.freed)}`, icon: "check", tone: "",
      body: `<div class="path-list">${res.results.map((r) => `<div><span>${U.esc(r.name)}</span><b class="${r.errors ? "warn-t" : "good-t"}">${U.bytes(r.freed)}</b></div>`).join("")}</div>
        ${failed.length ? `<div class="notice warn">${icon("info", "sm")}<div class="t">Some files were in use and were skipped (${failed.reduce((a, r) => a + r.errors, 0)} files). That's normal - close the apps and run cleanup again to get them too.</div></div>` : ""}`,
      actions: [{ label: "Done", kind: "primary" }],
    });
    App.afterChange();
    this.render(this.host, { rescan: true });
  },
};
