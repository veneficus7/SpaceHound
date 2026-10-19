/* Overview: welcome & drive picker, live "sonar" while scanning, bento dashboard after a scan. */

const TONES = {
  good: { a: "#34d399", b: "#22d3ee", glow: "rgba(52,211,153,.55)" },
  info: { a: "#60a5fa", b: "#8b5cf6", glow: "rgba(96,165,250,.5)" },
  warn: { a: "#fbbf24", b: "#fb923c", glow: "rgba(251,191,36,.45)" },
  bad: { a: "#fb7185", b: "#f472b6", glow: "rgba(251,113,133,.5)" },
};

Views.overview = {
  title: "Overview",
  icon: "overview",

  async render(host) {
    const s = App.summary;
    if (App.scan) { this.sonar(host); return; }
    host.innerHTML = `<div class="page">${s ? this.scanned(s) : this.welcome()}</div>`;
    this.bind(host, s);
    FX.countUp(host);
    // animate the health gauge after first paint (a timer also works when the window is in the background)
    setTimeout(() => {
      const arc = host.querySelector(".gauge circle.arc");
      if (arc) arc.style.strokeDashoffset = arc.dataset.target;
    }, 80);
  },

  bind(host, s) {
    host.querySelectorAll("[data-scan]").forEach((b) => (b.onclick = () => App.startScan([b.dataset.scan])));
    host.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => {
      const p = b.dataset.params ? JSON.parse(b.dataset.params) : {};
      App.go(b.dataset.go, p);
    }));
    const pick = host.querySelector("#pick-folder");
    if (pick) pick.onclick = () => App.chooseFolder();
    const all = host.querySelector("#scan-all");
    if (all) all.onclick = () => App.startScan(App.drives.filter((d) => d.ready && d.type === "fixed").map((d) => d.path));
    host.querySelectorAll("[data-insight]").forEach((b) => (b.onclick = () => {
      const a = s.insights[+b.dataset.insight].action || {};
      if (a.view) App.go(a.view, { node: a.node, cats: a.cats });
      else if (a.open) API.open_external(a.open);
      else if (a.elevate) App.elevate();
    }));
    host.querySelectorAll("[data-node]").forEach((b) => (b.onclick = () => App.go("explorer", { node: +b.dataset.node })));
    host.querySelectorAll("[data-file]").forEach((b) => (b.onclick = () => Actions.reveal(b.dataset.file)));
  },

  /* ------------------------------------------------------------ before the first scan */
  welcome() {
    const drives = App.drives.filter((d) => d.ready);
    const cards = drives.map((d) => {
      const frac = d.total ? d.used / d.total : 0;
      return `<div class="card drive-card">
        <div class="top"><div class="letter">${U.esc(d.path.slice(0, 2))}</div>
          <div style="flex:1;min-width:0"><div class="nm">${U.esc(d.label || "Local disk")}</div><div class="fs">${U.esc(d.fs)} · ${U.esc(d.type)} · ${U.bytes(d.total)}</div></div>
          ${Charts.ring(frac, { size: 58, stroke: 6 })}</div>
        ${R.sizeBar(frac, U.usageColor(frac))}
        <div class="nums"><span><b>${U.bytes(d.used)}</b> used</span><span><b>${U.bytes(d.free)}</b> free</span></div>
        ${d.recycle > 1 << 28 ? `<div class="small warn-t">${icon("trash", "sm")} ${U.bytes(d.recycle)} sitting in the Recycle Bin</div>` : ""}
        <button class="btn primary" data-scan="${U.esc(d.path)}">${icon("search", "sm")}Scan ${U.esc(d.path)}</button>
      </div>`;
    }).join("");
    const used = drives.reduce((a, d) => a + d.used, 0), total = drives.reduce((a, d) => a + d.total, 0);
    const features = [
      ["map", "Visual map", "Treemap, sunburst & bubbles of every folder.", null],
      ["sparkles", "Smart cleanup", "45 rules for caches, temp files & junk.", "cleanup"],
      ["copy", "Duplicates", "Byte-identical copies, safely removed.", "duplicates"],
      ["code", "Dev junk", "node_modules, build folders, venvs…", null],
      ["history", "History", "See exactly what grew since last time.", null],
      ["package", "Installed apps", "Real size of every program.", "apps"],
    ].map(([ic, t, d, go]) => `<div class="card feature" ${go ? `data-go="${go}"` : ""}><div class="fi">${icon(ic)}</div><div><h4>${t}</h4><p>${d}</p></div></div>`).join("");
    return `
      <div class="hero fade-in">
        <div class="art"><div class="orbit"><div class="ring"><i class="dot"></i></div><div class="ring"><i class="dot"></i></div><div class="ring"><i class="dot"></i></div>
          <div class="core">${icon("search")}</div></div></div>
        <h1>Let's sniff out what's<br><span class="grad-text">eating your disk.</span></h1>
        <p>You're using <b>${U.bytes(used)}</b> of <b>${U.bytes(total)}</b>. SpaceHound maps every folder in seconds, explains where the space went,
           and helps you win it back - safely.</p>
        <div class="btn-group">
          ${drives.length > 1 ? `<button class="btn primary lg" id="scan-all">${icon("layers")}Scan all drives</button>` : ""}
          <button class="btn lg" id="pick-folder">${icon("folder-open")}Scan a folder…</button>
          <span class="muted small" style="margin-left:6px">or press <span class="kbd">Ctrl</span> <span class="kbd">K</span></span>
        </div>
      </div>
      <h2 class="section">${icon("drive")}Your drives</h2>
      <div class="grid g3 stagger">${cards}</div>
      <h2 class="section">${icon("sparkles")}What SpaceHound can do</h2>
      <div class="grid g3 stagger">${features}</div>`;
  },

  /* ------------------------------------------------------------ live scan screen */
  sonar(host) {
    const paths = (App.scan && App.scan.paths) || [];
    host.innerHTML = `<div class="sonar-page fade-in"><div class="sonar-wrap">
      <div class="sonar" id="sonar"><div class="grid-ring"></div><div class="grid-ring"></div><div class="grid-ring"></div><div class="cross"></div>
        <div class="sweep"></div><i class="pulse"></i><i class="pulse"></i><div class="core">${icon("search")}</div></div>
      <h1 class="sonar-title">Sniffing through <span class="grad-text">${U.esc(paths.join(", "))}</span></h1>
      <p class="sonar-sub">Mapping every folder and file - this usually takes a few seconds.</p>
      <div class="sonar-stats">
        <div class="stat"><div class="label">${icon("file", "sm")}Files</div><div class="value" id="sn-files">0</div></div>
        <div class="stat"><div class="label">${icon("folder", "sm")}Folders</div><div class="value" id="sn-dirs">0</div></div>
        <div class="stat"><div class="label">${icon("pie", "sm")}Size found</div><div class="value" id="sn-bytes">0 B</div></div>
        <div class="stat"><div class="label">${icon("zap", "sm")}Speed</div><div class="value" id="sn-speed">-</div></div>
      </div>
      <div class="sonar-path" id="sn-path">Starting…</div>
      <button class="btn" id="sn-stop">${icon("stop", "sm")}Stop scanning</button>
    </div></div>`;
    host.querySelector("#sn-stop").onclick = () => { if (App.scan) API.cancel_job(App.scan.id); };
    FX.startBlips(host.querySelector("#sonar"));
    if (App.scan && App.scan.status) this.onScanProgress(App.scan.status);
  },

  onScanProgress(st) {
    const p = st.progress || {};
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("sn-files", U.num(p.files || 0));
    set("sn-dirs", U.num(p.dirs || 0));
    set("sn-bytes", U.bytes(p.bytes || 0));
    set("sn-speed", st.elapsed > 0.3 ? `${U.num(Math.round((p.files || 0) / st.elapsed))}/s` : "-");
    set("sn-path", p.phase === "finalizing" ? "Crunching the numbers…" : p.phase === "insights" ? "Looking for insights…" : p.current || "");
  },

  /* ------------------------------------------------------------ dashboard */
  healthCard(s) {
    const h = s.health;
    if (!h) return "";
    const tone = TONES[h.tone] || TONES.info;
    const size = 200, stroke = 16, r = (size - stroke) / 2, c = 2 * Math.PI * r;
    const target = c * (1 - h.score / 100);
    const roots = Object.keys(s.usage || {});
    const drive = (s.roots[0] || "").match(/^[A-Za-z]:/);
    const where = roots.length === 1 ? roots[0] : drive ? drive[0] + "\\" : "Your drive";
    const headline = roots.length > 1 ? `Your drives are ${Math.round((h.used / (h.total || 1)) * 100)}% full` : `${where} is ${Math.round((h.used / (h.total || 1)) * 100)}% full`;
    const parts = h.parts.map((p) => `<div class="part"><span class="k">${U.esc(p.label)}</span>
      ${R.sizeBar(p.score / p.max, p.score / p.max > .66 ? "linear-gradient(90deg,#34d399,#22d3ee)" : p.score / p.max > .33 ? "linear-gradient(90deg,#fbbf24,#fb923c)" : "linear-gradient(90deg,#fb7185,#f472b6)")}
      <span class="v">${p.score}/${p.max}</span></div>`).join("");
    const hasPrev = !!s.previous;
    return `<div class="card health span-7" style="--health-glow:${tone.glow}">
      <div class="gauge">
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
          <defs><linearGradient id="hg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${tone.a}"/><stop offset="1" stop-color="${tone.b}"/></linearGradient>
            <filter id="hglow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
          <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="${stroke}"/>
          <circle class="arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#hg)" stroke-width="${stroke}" stroke-linecap="round"
            stroke-dasharray="${c}" stroke-dashoffset="${c}" data-target="${target}" transform="rotate(-90 ${size / 2} ${size / 2})" filter="url(#hglow)"/>
        </svg>
        <div class="val"><div><b data-count="${h.score}" data-fmt="pct">0</b><span>Disk health</span></div></div>
      </div>
      <div class="info">
        <span class="tag" style="background:${U.hexToRgba(tone.a, .15)};color:${tone.a}">${icon(h.tone === "good" ? "check" : "alert", "sm")}${U.esc(h.label)}</span>
        <h2>${U.esc(headline)}</h2>
        <p>Only <b>${U.bytes(h.free)}</b> left. About <b class="grad-text">${U.bytes(h.reclaimable)}</b> looks reclaimable - caches, junk and duplicates.</p>
        <div class="parts">${parts}</div>
        <div class="btn-group">
          <button class="btn primary" data-go="cleanup">${icon("sparkles", "sm")}Clean up now</button>
          <button class="btn" data-go="duplicates">${icon("copy", "sm")}Find duplicates</button>
          ${hasPrev ? `<button class="btn ghost" data-go="history">${icon("trend", "sm")}What grew?</button>` : `<button class="btn ghost" data-go="map">${icon("map", "sm")}Visual map</button>`}
        </div>
      </div>
    </div>`;
  },

  scanned(s) {
    const usage = Object.entries(s.usage || {});
    let composition = "";
    if (usage.length === 1) {
      const [root, u] = usage[0];
      const segs = s.categories.map((c) => ({ label: c.label, value: c.size, color: c.color }));
      const hidden = Math.max(0, u.used - s.size);
      if (hidden > 0) segs.push({ label: "System / not readable", value: hidden, color: "#8b98ad", pattern: true });
      segs.push({ label: "Free", value: u.free, color: "rgba(139,148,173,.28)" });
      composition = `<div class="card pad span-12"><div class="row" style="margin-bottom:14px">
        <b style="font:650 15px var(--font-display)">${U.esc(root)} at a glance</b><span class="muted small">${U.bytes(u.used)} used of ${U.bytes(u.total)}</span></div>
        ${Charts.stackbar(segs, u.total)}</div>`;
    }
    const [sz, unit] = U.bytesParts(s.size);
    const freeU = usage.length === 1 ? usage[0][1] : null;
    const tiles = `
      <div class="stat"><div class="glow" style="background:#8b5cf6"></div><div class="label">${icon("pie", "sm")}Scanned</div><div class="value">${sz}<small>${unit}</small></div><div class="foot">${U.esc(s.roots.join(", "))}</div></div>
      <div class="stat"><div class="glow" style="background:#22d3ee"></div><div class="label">${icon("file", "sm")}Files</div><div class="value" data-count="${s.files}">0</div><div class="foot">${U.bytes(s.size / Math.max(1, s.files))} average</div></div>
      <div class="stat"><div class="glow" style="background:#f472b6"></div><div class="label">${icon("folder", "sm")}Folders</div><div class="value" data-count="${s.dirs}">0</div><div class="foot">${s.denied ? `${U.num(s.denied)} not readable` : "all readable"}</div></div>
      ${freeU ? `<div class="stat"><div class="glow" style="background:#34d399"></div><div class="label">${icon("drive", "sm")}Free space</div><div class="value">${U.bytesParts(freeU.free)[0]}<small>${U.bytesParts(freeU.free)[1]}</small></div><div class="foot">${U.pct(freeU.free / freeU.total)} of the drive</div></div>`
               : `<div class="stat"><div class="glow" style="background:#34d399"></div><div class="label">${icon("cloud", "sm")}Online-only</div><div class="value">${U.bytes(s.cloud)}</div><div class="foot">no local space used</div></div>`}
      <div class="stat"><div class="glow" style="background:#fbbf24"></div><div class="label">${icon("zap", "sm")}Scan time</div><div class="value">${U.duration(s.duration)}</div><div class="foot">${U.num(Math.round(s.files / Math.max(0.1, s.duration)))} files/s</div></div>`;
    const insights = (s.insights || []).map((i, n) => `
      <div class="insight ${i.tone}">
        <div class="ii">${icon(i.icon in ICONS ? i.icon : "info")}</div>
        <div style="min-width:0"><h4>${U.esc(i.title)}</h4><p>${U.esc(i.text)}</p>
          ${i.action ? `<div class="act"><button class="btn sm" data-insight="${n}">Show me${icon("chev-right", "sm")}</button></div>` : ""}</div>
      </div>`).join("");
    const donut = Charts.donut(s.categories.map((c) => ({ label: c.label, value: c.size, color: c.color, key: c.key })),
      { size: 172, thickness: 26, center: U.bytes(s.size), sub: "scanned" });
    const legend = s.categories.slice(0, 7).map((c) => `<div class="dl" data-go="largest" data-params='${JSON.stringify({ cats: [c.key] })}' style="color:${c.color}">
      <i style="background:${c.color}"></i><span class="ellipsis" style="color:var(--text)">${U.esc(c.label)}</span><b style="color:var(--text)">${U.bytes(c.size)}</b><span>${U.pct(c.size / (s.size || 1), 0)}</span></div>`).join("");
    const maxDeep = Math.max(1, ...s.deep.map((d) => d.size));
    const deep = s.deep.slice(0, 8).map((d) => `<div class="lb" data-node="${d.id}"><div class="n"><b>${U.esc(d.name)}</b><span>${U.esc(d.path)}</span></div>
      <div class="s">${U.bytes(d.size)}</div>${R.sizeBar(d.size / maxDeep)}</div>`).join("");
    const maxFile = Math.max(1, ...s.top_files.map((f) => f.size));
    const files = s.top_files.slice(0, 8).map((f) => `<div class="lb" data-file="${U.esc(f.path)}" title="Show in File Explorer"><div class="n"><b>${U.esc(f.name)}</b><span>${U.esc(f.folder)}</span></div>
      <div class="s">${U.bytes(f.size)}</div>${R.sizeBar(f.size / maxFile, (App.cats[f.cat] || {}).color)}</div>`).join("");
    const age = Charts.columns(s.age.map((a, i) => ({ label: a.label, value: a.size, sub: `${U.num(a.count)} files`,
      color: ["#22d3ee", "#38bdf8", "#8b5cf6", "#a855f7", "#f472b6", "#fb7185"][i] })), { height: 190 });
    const quick = [["sparkles", "Smart cleanup", "Caches, temp & Recycle Bin", "cleanup"], ["copy", "Duplicates", "Identical files", "duplicates"],
      ["code", "Dev junk", "Rebuildable project folders", "devjunk"], ["map", "Visual map", "See everything at once", "map"]]
      .map(([ic, t, d, go]) => `<div class="card feature lift" data-go="${go}" style="padding:14px"><div class="fi">${icon(ic)}</div><div><h4>${t}</h4><p>${d}</p></div></div>`).join("");
    return `
      <div class="bento stagger">
        ${this.healthCard(s) || `<div class="card pad span-7"><h2 class="section" style="margin:0">${U.esc(s.roots.join(", "))}</h2></div>`}
        <div class="card span-5"><div class="card-head"><h3>${icon("pie", "sm")}Where the space goes</h3></div>
          <div class="card-body donut-wrap">${donut}<div class="donut-legend">${legend}</div></div></div>
        <div class="span-12 grid g5">${tiles}</div>
        ${composition}
      </div>
      ${insights ? `<h2 class="section">${icon("sparkles")}Why is my disk full? <span class="sub">Automatic findings from this scan</span></h2><div class="insights stagger">${insights}</div>` : ""}
      <div class="bento stagger" style="margin-top:18px">
        <div class="card span-6"><div class="card-head"><h3>${icon("folder", "sm")}Biggest folders</h3><span class="sub">most specific first</span></div>
          <div class="card-body list-bars">${deep}</div></div>
        <div class="card span-6"><div class="card-head"><h3>${icon("files", "sm")}Largest files</h3></div>
          <div class="card-body list-bars">${files}</div></div>
        <div class="card span-7"><div class="card-head"><h3>${icon("clock", "sm")}How old is your data</h3><span class="sub">by last modification</span></div>
          <div class="card-body">${age}</div></div>
        <div class="span-5 grid g2" style="gap:12px;align-content:start">${quick}</div>
      </div>`;
  },
};
