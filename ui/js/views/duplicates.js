/* Duplicate finder: setup -> progress -> grouped results with smart selection. */

Views.duplicates = {
  title: "Duplicates",
  icon: "copy",
  badge() { const r = App.state.dupsResult; return r && r.groups.length ? U.bytes(r.wasted) : ""; },

  async render(host, params) {
    const st = (App.state.dups = App.state.dups || { roots: null, min: App.settings.dup_min_mb || 1, cats: [], skip: App.settings.dup_skip_system !== false, page: 0, sort: "wasted", cat: "" });
    this.host = host;
    if (params.roots) { st.roots = params.roots.slice(); params.roots = null; App.state.dupsResult = null; }
    if (!st.roots) st.roots = App.summary ? App.summary.roots.slice() : [];
    if (!App.state.dupsResult) {
      try { App.state.dupsResult = await API.duplicates_result(); } catch (_) {}
    }
    if (App.state.dupsResult) this.results(); else this.setup();
  },

  refresh() {
    API.duplicates_result().then((r) => { App.state.dupsResult = r; if (App.view === "duplicates") { if (r) this.results(); else this.setup(); } });
  },

  setup() {
    const st = App.state.dups;
    const host = this.host;
    const cats = [["", "All files"], ["image", "Photos"], ["video", "Videos"], ["audio", "Music"], ["document", "Documents"], ["archive", "Archives"], ["app", "Installers"], ["diskimage", "Disk images"]];
    host.innerHTML = `<div class="page fade-in" style="max-width:900px">
      <div class="hero" style="padding:28px 30px">
        <h1 style="font-size:24px">Find identical files</h1>
        <p style="margin-bottom:0">SpaceHound groups files by size, compares the first and last 64 KB, then verifies the full content with a BLAKE2 hash.
           Only byte-for-byte identical files are reported - and nothing is deleted without your say-so.</p>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="settings-row"><div><h4>Where to look</h4><p>Folders and drives to compare against each other.</p>
          <div class="list-input" style="margin-top:10px" id="roots">${st.roots.map((r, i) => `<div class="li"><span>${U.esc(r)}</span><button class="btn ghost sm icon" data-rm="${i}">${icon("x", "sm")}</button></div>`).join("") || `<div class="muted small">No folders yet.</div>`}</div></div>
          <div class="btn-group"><button class="btn sm" id="add">${icon("plus", "sm")}Add folder</button>${App.summary ? `<button class="btn sm ghost" id="usescan">Use scanned</button>` : ""}</div></div>
        <div class="settings-row"><div><h4>Minimum file size</h4><p>Skipping tiny files makes the search much faster. Scan results are reused for files ≥ 64 KB.</p></div>
          <select class="input" id="min">${[[0.1, "100 KB"], [1, "1 MB"], [10, "10 MB"], [100, "100 MB"], [1024, "1 GB"]].map(([v, l]) => `<option value="${v}" ${+st.min === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="settings-row"><div><h4>File types</h4><div class="chips" style="margin-top:8px" id="cats">${cats.map(([k, l]) => `<span class="chip ${(k === "" && !st.cats.length) || st.cats.includes(k) ? "on" : ""}" data-cat="${k}">${U.esc(l)}</span>`).join("")}</div></div><div></div></div>
        <div class="settings-row"><div><h4>Skip system & app folders</h4><p>Windows, Program Files, ProgramData and AppData contain intentional copies that apps need.</p></div>
          <label class="toggle"><input type="checkbox" id="skip" ${st.skip ? "checked" : ""}><span></span></label></div>
      </div>
      <div style="margin-top:18px;text-align:right"><button class="btn primary lg" id="go" ${st.roots.length ? "" : "disabled"}>${icon("search")}Find duplicates</button></div>
    </div>`;
    host.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { st.roots.splice(+b.dataset.rm, 1); this.setup(); }));
    host.querySelector("#add").onclick = async () => {
      const p = App.info.mode === "webview" ? await API.pick_folder() : await UI.prompt({ title: "Add folder", label: "Folder path", placeholder: "D:\\Photos" });
      if (p && !st.roots.includes(p)) { st.roots.push(p); this.setup(); }
    };
    const us = host.querySelector("#usescan");
    if (us) us.onclick = () => { st.roots = App.summary.roots.slice(); this.setup(); };
    host.querySelector("#min").onchange = (e) => (st.min = +e.target.value);
    host.querySelector("#skip").onchange = (e) => (st.skip = e.target.checked);
    host.querySelectorAll("[data-cat]").forEach((c) => (c.onclick = () => {
      const k = c.dataset.cat;
      if (!k) st.cats = []; else st.cats = st.cats.includes(k) ? st.cats.filter((x) => x !== k) : [...st.cats, k];
      this.setup();
    }));
    host.querySelector("#go").onclick = () => this.run();
  },

  async run() {
    const st = App.state.dups;
    const host = this.host;
    let id;
    try { id = await API.start_duplicates({ roots: st.roots, min_mb: st.min, cats: st.cats, skip_system: st.skip }); }
    catch (err) { UI.toast(U.esc(err.message), "bad"); return; }
    const phases = { collect: "Collecting files", partial: "Comparing samples", full: "Verifying full contents", finishing: "Grouping results" };
    try {
      await inlineJob(host, id, {
        title: "Searching for duplicates",
        describe: (p) => {
          const steps = ["collect", "partial", "full", "finishing"];
          const cur = steps.indexOf(p.phase || "collect");
          const pipe = steps.map((s, i) => `<span class="st ${i === cur ? "on" : i < cur ? "done" : ""}">${i < cur ? icon("check", "sm") : ""}${phases[s]}</span>`).join(icon("chev-right", "sm"));
          let detail = "";
          if (p.phase === "partial") detail = `${U.num(p.done || 0)} / ${U.num(p.total || 0)} candidates`;
          else if (p.phase === "full") detail = `${U.bytes(p.bytes_done || 0)} / ${U.bytes(p.bytes_total || 0)} hashed`;
          else if (p.files) detail = `${U.num(p.files)} files looked at`;
          return `<div class="pipeline" style="margin-bottom:8px">${pipe}</div>${detail}`;
        },
      });
      App.state.dupsResult = await API.duplicates_result();
      st.page = 0;
      App.renderSidebar();
      this.results();
    } catch (err) {
      if (!err.cancelled) UI.toast(U.esc(err.message), "bad");
      this.setup();
    }
  },

  /* ------------------------------------------------------------ results */
  results() {
    const st = App.state.dups;
    const res = App.state.dupsResult;
    const host = this.host;
    if (!this.sel || this.selFor !== res) {
      this.sel = new Selection(() => this.updateSel());
      this.selFor = res;
    }
    let groups = res.groups.filter((g) => !st.cat || g.cat === st.cat);
    if (st.sort === "size") groups = groups.slice().sort((a, b) => b.size - a.size);
    if (st.sort === "count") groups = groups.slice().sort((a, b) => b.count - a.count);
    this.view = groups;
    const per = 40;
    const pages = Math.max(1, Math.ceil(groups.length / per));
    st.page = Math.min(st.page, pages - 1);
    const slice = groups.slice(st.page * per, st.page * per + per);
    const catsPresent = [...new Set(res.groups.map((g) => g.cat))];
    host.innerHTML = `<div class="page fade-in">
      <div class="grid g4">
        <div class="stat"><div class="glow" style="background:var(--bad)"></div><div class="label">${icon("copy", "sm")}Reclaimable</div><div class="value">${U.bytes(res.wasted)}</div><div class="foot">by keeping one copy of each</div></div>
        <div class="stat"><div class="label">${icon("layers", "sm")}Groups</div><div class="value">${U.num(res.groups.length)}</div><div class="foot">sets of identical files</div></div>
        <div class="stat"><div class="label">${icon("files", "sm")}Files</div><div class="value">${U.num(res.files)}</div><div class="foot">of ${U.num(res.candidates)} compared</div></div>
        <div class="stat"><div class="label">${icon("zap", "sm")}Search time</div><div class="value">${U.duration(res.elapsed)}</div><div class="foot ellipsis">${U.esc(res.roots.join(", "))}</div></div>
      </div>
      <div class="toolbar" style="margin-top:16px">
        <button class="btn primary" id="auto">${icon("sparkles", "sm")}Auto-select${icon("chev-down", "sm")}</button>
        <button class="btn" id="clear">Clear selection</button>
        <select class="input sm" id="cat"><option value="">All types</option>${catsPresent.map((c) => `<option value="${c}" ${st.cat === c ? "selected" : ""}>${U.esc(App.catLabel(c))}</option>`).join("")}</select>
        <select class="input sm" id="sort">${[["wasted", "Most space wasted"], ["size", "Largest files"], ["count", "Most copies"]].map(([k, l]) => `<option value="${k}" ${st.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select>
        <div class="spacer"></div>
        <button class="btn sm" id="export">${icon("download", "sm")}Export</button>
        <button class="btn sm" id="new">${icon("search", "sm")}New search</button>
      </div>
      ${res.groups.length ? "" : R.empty("check", "No duplicates found", "Every file in these folders is unique. Nice and tidy!")}
      <div id="groups">${slice.map((g) => this.groupHtml(g)).join("")}</div>
      ${pages > 1 ? `<div class="row" style="justify-content:center;margin-top:12px"><button class="btn sm" id="prev" ${st.page ? "" : "disabled"}>Previous</button>
        <span class="text-2 small">Page ${st.page + 1} of ${pages}</span><button class="btn sm" id="next" ${st.page < pages - 1 ? "" : "disabled"}>Next</button></div>` : ""}
    </div>`;
    host.querySelector("#auto").onclick = (e) => this.autoMenu(e);
    host.querySelector("#clear").onclick = () => { this.sel.clear(); this.results(); };
    host.querySelector("#cat").onchange = (e) => { st.cat = e.target.value; st.page = 0; this.results(); };
    host.querySelector("#sort").onchange = (e) => { st.sort = e.target.value; st.page = 0; this.results(); };
    host.querySelector("#export").onclick = async () => { const p = await API.export("duplicates"); if (p) UI.toast(`Saved ${U.esc(p)}`, "good"); };
    host.querySelector("#new").onclick = () => { App.state.dupsResult = null; this.setup(); };
    const prev = host.querySelector("#prev"), next = host.querySelector("#next");
    if (prev) prev.onclick = () => { st.page--; this.results(); host.scrollTop = 0; };
    if (next) next.onclick = () => { st.page++; this.results(); host.scrollTop = 0; };
    const gEl = host.querySelector("#groups");
    gEl.onclick = (e) => {
      const f = e.target.closest("[data-file]");
      const act = e.target.closest("[data-act]");
      if (act) {
        const path = act.dataset.path;
        if (act.dataset.act === "reveal") Actions.reveal(path);
        if (act.dataset.act === "open") Actions.open(path);
        return;
      }
      if (f) {
        const g = res.groups[+f.dataset.g];
        const file = g.files[+f.dataset.file];
        this.sel.toggle({ path: file.path, size: g.size, g: g.id, mtime: file.mtime });
        return;
      }
      const head = e.target.closest("[data-keep]");
      if (head) {
        const g = res.groups[+head.dataset.keep];
        this.keepOnly(g, +head.dataset.idx);
      }
    };
    this.loadThumbs(slice);
    this.updateSel();
  },

  groupHtml(g) {
    const name = U.basename(g.files[0].path);
    const isImg = g.cat === "image";
    return `<div class="card dup-group" data-group="${g.id}">
      <div class="dup-head">
        <div class="dup-thumb" data-thumb="${isImg ? U.esc(g.files[0].path) : ""}">${icon(CAT_ICONS[g.cat] || "file", "lg")}</div>
        <div style="flex:1;min-width:0"><div class="ellipsis" style="font-weight:620">${U.esc(name)}</div>
          <div class="small text-2">${g.count} copies · ${U.bytes(g.size)} each · ${R.catBadge(g.cat)}</div></div>
        <div style="text-align:right"><div style="font:650 16px var(--font-display)" class="bad-t">${U.bytes(g.wasted)}</div><div class="muted small">wasted</div></div>
      </div>
      <div class="dup-files">${g.files.map((f, i) => {
        const on = this.sel.has({ path: f.path });
        return `<div class="dup-file ${on ? "sel" : ""}" data-g="${g.id}" data-file="${i}">
          <input type="checkbox" class="check" ${on ? "checked" : ""}>
          <div class="p"><b>${U.esc(U.basename(f.path))}</b><span title="${U.esc(f.path)}">${U.esc(U.dirname(f.path))}</span></div>
          <div class="small text-2">${U.date(f.mtime)}${f.linked ? ` <span class="badge info">hard link</span>` : ""}</div>
          <div class="row" style="gap:2px">
            <button class="btn ghost sm" data-keep="${g.id}" data-idx="${i}" title="Select every other copy">Keep this</button>
            <button class="btn ghost sm icon" data-act="open" data-path="${U.esc(f.path)}" title="Open">${icon("external", "sm")}</button>
            <button class="btn ghost sm icon" data-act="reveal" data-path="${U.esc(f.path)}" title="Show in Explorer">${icon("folder", "sm")}</button></div>
        </div>`;
      }).join("")}</div></div>`;
  },

  async loadThumbs(groups) {
    for (const g of groups) {
      if (g.cat !== "image") continue;
      const el = this.host.querySelector(`[data-group="${g.id}"] .dup-thumb`);
      if (!el) continue;
      const src = await API.image_preview(g.files[0].path, 6 << 20);
      if (!src || !el.isConnected) continue;
      const img = new Image();
      img.alt = "";
      img.onload = () => { if (el.isConnected) { el.innerHTML = ""; el.append(img); } };
      img.src = src; // unreadable / corrupt images simply keep the file-type icon
    }
  },

  keepOnly(g, idx) {
    g.files.forEach((f, i) => {
      const item = { path: f.path, size: g.size, g: g.id, mtime: f.mtime };
      if (i === idx) this.sel.map.delete(f.path); else this.sel.map.set(f.path, item);
    });
    this.sel.changed();
  },

  autoMenu(e) {
    const strat = (label, pick) => ({ label, icon: "sparkles", onClick: () => this.autoSelect(pick) });
    UI.menu(e, [
      strat("Keep the newest copy", (fs) => fs.reduce((a, b) => (b.mtime > a.mtime ? b : a))),
      strat("Keep the oldest copy (the original)", (fs) => fs.reduce((a, b) => (b.mtime < a.mtime ? b : a))),
      strat("Keep the copy with the shortest path", (fs) => fs.reduce((a, b) => (b.path.length < a.path.length ? b : a))),
      strat("Keep copies outside Downloads", (fs) => fs.find((f) => !/\\downloads\\/i.test(f.path)) || fs[0]),
      { label: "Keep the copy inside a folder…", icon: "folder", onClick: async () => {
        const folder = await UI.prompt({ title: "Keep copies in…", label: "Folder (copies inside it are kept)", placeholder: "D:\\Photos" });
        if (!folder) return;
        const low = folder.toLowerCase().replace(/[\\/]+$/, "") + "\\";
        this.autoSelect((fs) => fs.find((f) => f.path.toLowerCase().startsWith(low)) || null);
      } },
    ], "Select all copies except the one to keep");
  },

  autoSelect(pickKeep) {
    let n = 0;
    for (const g of this.view) {
      const keep = pickKeep(g.files);
      if (!keep) continue;
      for (const f of g.files) {
        if (f === keep || f.linked) this.sel.map.delete(f.path);
        else { this.sel.map.set(f.path, { path: f.path, size: g.size, g: g.id, mtime: f.mtime }); n++; }
      }
    }
    this.sel.changed();
    this.results();
    UI.toast(`Selected ${U.num(n)} duplicate files`, "info", 2000);
  },

  updateSel() {
    const host = this.host;
    host.querySelectorAll(".dup-file").forEach((row) => {
      const g = App.state.dupsResult.groups[+row.dataset.g];
      const f = g && g.files[+row.dataset.file];
      const on = f && this.sel.has({ path: f.path });
      row.classList.toggle("sel", !!on);
      const ck = row.querySelector("input");
      if (ck) ck.checked = !!on;
    });
    renderSelBar(host, this.sel, [
      { label: "Move to…", icon: "move", onClick: () => this.act("move") },
      { label: "Replace with hard links", icon: "link", onClick: () => this.act("link") },
      { label: "Recycle Bin", icon: "trash", onClick: () => this.act("recycle") },
      { label: "Delete permanently", icon: "trash-x", kind: "danger", onClick: () => this.act("permanent") },
    ]);
  },

  /* never allow every copy of a group to be removed */
  fullGroups() {
    const res = App.state.dupsResult;
    const by = {};
    this.sel.items.forEach((i) => (by[i.g] = (by[i.g] || 0) + 1));
    return Object.entries(by).filter(([g, n]) => res.groups[+g] && n >= res.groups[+g].files.length).map(([g]) => res.groups[+g]);
  },

  async act(kind) {
    const full = this.fullGroups();
    if (full.length) {
      await UI.modal({
        title: "Every copy is selected", icon: "alert", tone: "warn",
        body: `<p>In ${full.length} group(s) you selected <b>all</b> copies - that would remove the file completely. Keep at least one copy:</p>
          <div class="path-list">${full.slice(0, 20).map((g) => `<div><span>${U.esc(U.basename(g.files[0].path))}</span><b>${g.count} copies</b></div>`).join("")}</div>`,
        actions: [{ label: "OK", kind: "primary" }],
      });
      return;
    }
    const items = this.sel.items;
    if (kind === "move") return Actions.move(items);
    if (kind === "recycle" || kind === "permanent") return Actions.delete(items, { mode: kind, source: "duplicates" });
    if (kind === "link") {
      const res = App.state.dupsResult;
      const byGroup = {};
      items.forEach((i) => (byGroup[i.g] = byGroup[i.g] || []).push(i));
      const groups = [];
      for (const [gid, sel] of Object.entries(byGroup)) {
        const g = res.groups[+gid];
        const keep = g.files.find((f) => !sel.some((s) => s.path === f.path));
        const drive = (p) => p.slice(0, 2).toLowerCase();
        const targets = sel.filter((s) => drive(s.path) === drive(keep.path)).map((s) => ({ path: s.path, mtime: s.mtime }));
        if (targets.length) groups.push({ keep: keep.path, size: g.size, targets });
      }
      const n = groups.reduce((a, g) => a + g.targets.length, 0);
      if (!n) { UI.toast("Hard links only work when the copies are on the same drive.", "warn"); return; }
      const ok = await UI.confirm({
        title: `Replace ${n} duplicate(s) with hard links?`, icon: "link",
        message: `Every path keeps working and shows the same file, but the data is stored only once on disk.
          Saves about <b>${U.bytes(groups.reduce((a, g) => a + g.size * g.targets.length, 0))}</b>.`,
        details: `<div class="notice info">${icon("info", "sm")}<div class="t">Hard-linked files share their contents: editing one changes all of them. Ideal for photo libraries, installers and media that never change.</div></div>`,
        confirmLabel: "Create hard links",
      });
      if (!ok) return;
      const id = await API.start_hardlink(groups);
      const r = await UI.runJob(id, { title: "Creating hard links", icon: "link", describe: (p) => `${p.done || 0} / ${p.total || 0} groups` });
      if (!r) return;
      if (r.saved > 0) FX.confetti();
      UI.toast(`Linked <b>${r.linked}</b> files, saved <b>${U.bytes(r.saved)}</b>.${r.failed.length ? ` ${r.failed.length} failed.` : ""}`, r.failed.length ? "warn" : "good");
      this.sel.clear();
      App.state.dupsResult = await API.duplicates_result();
      this.results();
    }
  },
};
