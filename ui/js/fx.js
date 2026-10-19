/* Motion & delight: count-up numbers, confetti bursts, sonar blips. */

const FX = (() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ease = (t) => 1 - Math.pow(1 - t, 3);

  /* animate every [data-count] element inside root: data-count=<number>, data-fmt=bytes|num */
  function countUp(root = document) {
    root.querySelectorAll("[data-count]").forEach((el) => {
      const to = Number(el.dataset.count) || 0;
      const fmt = el.dataset.fmt === "bytes" ? (v) => U.bytes(v) : el.dataset.fmt === "pct" ? (v) => Math.round(v) + "" : (v) => U.num(Math.round(v));
      if (reduced || to === 0) { el.textContent = fmt(to); return; }
      const dur = Number(el.dataset.dur) || 1100;
      const t0 = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - t0) / dur);
        el.textContent = fmt(to * ease(t));
        if (t < 1 && el.isConnected) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  /* confetti burst from (x, y) - defaults to the centre of the screen */
  function confetti(x, y, count = 140) {
    if (reduced) return;
    const c = document.getElementById("fx");
    const dpr = window.devicePixelRatio || 1;
    c.width = innerWidth * dpr;
    c.height = innerHeight * dpr;
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    x = x ?? innerWidth / 2;
    y = y ?? innerHeight / 2.6;
    const colors = ["#8b5cf6", "#22d3ee", "#f472b6", "#fbbf24", "#34d399", "#a78bfa", "#ffffff"];
    const parts = Array.from({ length: count }, () => {
      const a = Math.random() * Math.PI * 2;
      const v = 4 + Math.random() * 9;
      return { x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 6, r: 3 + Math.random() * 5, rot: Math.random() * 6,
               vr: (Math.random() - .5) * .4, c: colors[(Math.random() * colors.length) | 0], life: 0, shape: Math.random() < .5 };
    });
    let frame = 0;
    const tick = () => {
      frame++;
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      let alive = 0;
      for (const p of parts) {
        p.vy += 0.28; p.vx *= 0.985; p.vy *= 0.985;
        p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.life++;
        const alpha = Math.max(0, 1 - p.life / 150);
        if (alpha <= 0 || p.y > innerHeight + 20) continue;
        alive++;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.c;
        if (p.shape) ctx.fillRect(-p.r, -p.r / 2.5, p.r * 2, p.r / 1.25);
        else { ctx.beginPath(); ctx.arc(0, 0, p.r / 1.6, 0, Math.PI * 2); ctx.fill(); }
        ctx.restore();
      }
      if (alive && frame < 260) requestAnimationFrame(tick);
      else ctx.clearRect(0, 0, innerWidth, innerHeight);
    };
    requestAnimationFrame(tick);
  }

  /* random blips on the scan sonar */
  let blipTimer = null;
  function startBlips(el) {
    stopBlips();
    blipTimer = setInterval(() => {
      if (!el.isConnected) { stopBlips(); return; }
      const b = document.createElement("i");
      b.className = "blip" + (Math.random() < .35 ? " v" : "");
      const a = Math.random() * Math.PI * 2, r = 18 + Math.random() * 30;
      b.style.left = `calc(${50 + Math.cos(a) * r}% - 4px)`;
      b.style.top = `calc(${50 + Math.sin(a) * r}% - 4px)`;
      el.append(b);
      setTimeout(() => b.remove(), 2300);
    }, 260);
  }
  function stopBlips() { if (blipTimer) clearInterval(blipTimer); blipTimer = null; }

  return { countUp, confetti, startBlips, stopBlips };
})();

/* ================================================================== command palette */
const Palette = (() => {
  let el = null;
  let items = [];
  let idx = 0;

  function commands(q) {
    const out = [];
    const add = (group, label, ic, run, hint = "") => out.push({ group, label, ic, run, hint });
    for (const [, ids] of NAV) {
      for (const id of ids) {
        const v = Views[id];
        if (v) add("Go to", v.title, v.icon, () => App.go(id), v.needsScan && !App.summary ? "needs a scan" : "");
      }
    }
    add("Go to", "Settings", "settings", () => App.go("settings"));
    App.drives.filter((d) => d.ready).forEach((d) =>
      add("Scan", `Scan ${d.path} ${d.label ? "(" + d.label + ")" : ""}`, "drive", () => App.startScan([d.path]), U.bytes(d.used) + " used"));
    add("Scan", "Scan a folder…", "folder-open", () => App.chooseFolder());
    if (App.summary) add("Scan", "Rescan current location", "refresh", () => App.startScan(App.summary.roots), "F5");
    add("Actions", "Toggle dark / light theme", "moon", () => App.toggleTheme());
    if (App.summary) add("Actions", "Export HTML report", "download", async () => { const p = await API.export("report"); if (p) UI.toast(`Saved ${U.esc(p)}`, "good"); });
    if (App.info && !App.info.admin) add("Actions", "Restart as administrator", "shield", () => App.elevate());
    q = q.trim().toLowerCase();
    let res = q ? out.filter((c) => c.label.toLowerCase().includes(q) || c.group.toLowerCase().includes(q)) : out;
    if (q && App.summary) res.unshift({ group: "Search", label: `Search files & folders for “${q}”`, ic: "search", run: () => App.go("search", { q }) });
    return res;
  }

  function render() {
    const q = el.querySelector("input").value;
    items = commands(q);
    idx = Math.min(idx, Math.max(0, items.length - 1));
    let last = "";
    el.querySelector(".list").innerHTML = items.map((c, i) => {
      const grp = c.group !== last ? `<div class="grp">${U.esc(c.group)}</div>` : "";
      last = c.group;
      return `${grp}<div class="it ${i === idx ? "on" : ""}" data-i="${i}"><div class="ic">${icon(c.ic, "sm")}</div><b>${U.esc(c.label)}</b><span class="hint">${U.esc(c.hint || "")}</span></div>`;
    }).join("") || `<div class="grp">No matches</div>`;
    const on = el.querySelector(".it.on");
    if (on) on.scrollIntoView({ block: "nearest" });
  }

  function run(i) {
    const c = items[i];
    close();
    if (c) c.run();
  }

  function open() {
    if (el) return;
    idx = 0;
    el = U.el(`<div class="palette"><div class="box">
      <div class="in">${icon("search", "lg")}<input placeholder="Type a command, a view or a file name…" spellcheck="false"><kbd>Esc</kbd></div>
      <div class="list"></div>
      <div class="foot"><span><kbd>↑</kbd> <kbd>↓</kbd> navigate</span><span><kbd>Enter</kbd> run</span><span><kbd>Ctrl</kbd> <kbd>K</kbd> toggle</span></div>
    </div></div>`);
    document.body.append(el);
    const input = el.querySelector("input");
    input.oninput = () => { idx = 0; render(); };
    input.onkeydown = (e) => {
      if (e.key === "ArrowDown") { idx = Math.min(items.length - 1, idx + 1); render(); e.preventDefault(); }
      if (e.key === "ArrowUp") { idx = Math.max(0, idx - 1); render(); e.preventDefault(); }
      if (e.key === "Enter") { run(idx); e.preventDefault(); }
      if (e.key === "Escape") close();
    };
    el.addEventListener("mousedown", (e) => { if (e.target === el) close(); });
    el.querySelector(".list").onclick = (e) => { const it = e.target.closest(".it"); if (it) run(+it.dataset.i); };
    el.querySelector(".list").onmousemove = (e) => {
      const it = e.target.closest(".it");
      if (it && +it.dataset.i !== idx) { idx = +it.dataset.i; el.querySelectorAll(".it").forEach((x) => x.classList.toggle("on", x === it)); }
    };
    render();
    setTimeout(() => input.focus(), 10);
  }

  function close() { if (el) { el.remove(); el = null; } }
  function toggle() { el ? close() : open(); }
  return { open, close, toggle };
})();
