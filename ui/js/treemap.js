/* Canvas treemap (squarified, nested, cushion shading) and sunburst.
   Data nodes from the backend: {i?, n, s, t (0 dir, 1 file, 2 rest), k?, m?, c?} */

class SpaceMap {
  constructor(stage, opts = {}) {
    this.stage = stage;
    this.opts = opts;
    this.mode = opts.mode || "treemap";
    this.colorBy = opts.colorBy || "type";
    this.base = document.createElement("canvas");
    this.over = document.createElement("canvas");
    stage.append(this.base, this.over);
    this.rects = [];
    this.arcs = [];
    this.hover = null;
    this.data = null;
    this.rootPath = "";
    this._onMove = (e) => this.move(e);
    this._onLeave = () => { this.setHover(null); UI.hideTip(); };
    this._onClick = (e) => this.click(e, false);
    this._onDbl = (e) => this.click(e, true);
    this._onCtx = (e) => { e.preventDefault(); const it = this.hit(e); if (it && this.opts.onContext) this.opts.onContext(e, this.describe(it)); };
    this.over.addEventListener("mousemove", this._onMove);
    this.over.addEventListener("mouseleave", this._onLeave);
    this.over.addEventListener("click", this._onClick);
    this.over.addEventListener("dblclick", this._onDbl);
    this.over.addEventListener("contextmenu", this._onCtx);
    this.ro = new ResizeObserver(() => this.render());
    this.ro.observe(stage);
  }

  destroy() {
    this.ro.disconnect();
    UI.hideTip();
    this.stage.innerHTML = "";
  }

  setData(data, rootPath) {
    this.data = data;
    this.rootPath = rootPath || "";
    const link = (n, p) => { n._p = p; if (n.c) n.c.forEach((c) => link(c, n)); };
    link(data, null);
    this.topHue = new Map();
    (data.c || []).forEach((c, i) => this.topHue.set(c, (i * 47 + 255) % 360));
    this.render();
  }

  setMode(mode) { this.mode = mode; this.render(); }
  setColorBy(c) { this.colorBy = c; this.render(); }

  /* ---------------------------------------------------------------- colours */
  catColor(k) { return (App.catList[k] && App.catList[k].color) || "#6b7385"; }

  ageColor(m) {
    if (!m) return "#6b7385";
    const days = Math.max(0, (Date.now() / 1000 - m) / 86400);
    const t = Math.min(1, Math.log10(1 + days) / Math.log10(1 + 2500));
    const stops = [[34, 211, 238], [139, 92, 246], [244, 63, 94], [148, 90, 60]];
    const seg = Math.min(stops.length - 2, Math.floor(t * (stops.length - 1)));
    const f = t * (stops.length - 1) - seg;
    const a = stops[seg], b = stops[seg + 1];
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  topOf(n) { let x = n; while (x._p && x._p !== this.data) x = x._p; return x; }

  fileColor(n) {
    if (n.t === 2) return n.k != null && this.colorBy === "type" ? U.shade(this.catColor(n.k), -0.25) : "#4a5262";
    if (this.colorBy === "age") return this.ageColor(n.m);
    if (this.colorBy === "folder") {
      const hue = this.topHue.get(this.topOf(n)) ?? 260;
      return `hsl(${hue} 62% 58%)`;
    }
    if (n.t === 0) return n.k != null ? this.catColor(n.k) : "#5d6475";
    return this.catColor(n.k);
  }

  /* ---------------------------------------------------------------- layout */
  static squarify(items, x, y, w, h, out) {
    const total = items.reduce((a, c) => a + c.s, 0);
    if (total <= 0 || w < 1 || h < 1) return;
    const scale = (w * h) / total;
    const list = items.map((c) => ({ n: c, a: c.s * scale })).filter((c) => c.a > 0.5);
    let row = [];
    let i = 0;
    const worst = (r, side) => {
      let s = 0, mx = 0, mn = Infinity;
      for (const it of r) { s += it.a; if (it.a > mx) mx = it.a; if (it.a < mn) mn = it.a; }
      const s2 = s * s, side2 = side * side;
      return Math.max((side2 * mx) / s2, s2 / (side2 * mn));
    };
    const flush = () => {
      const s = row.reduce((a, it) => a + it.a, 0);
      if (w >= h) {
        const rw = s / h;
        let cy = y;
        for (const it of row) { const rh = it.a / rw; out.push([it.n, x, cy, rw, rh]); cy += rh; }
        x += rw; w -= rw;
      } else {
        const rh = s / w;
        let cx = x;
        for (const it of row) { const rww = it.a / rh; out.push([it.n, cx, y, rww, rh]); cx += rww; }
        y += rh; h -= rh;
      }
      row = [];
    };
    while (i < list.length) {
      const side = Math.min(w, h);
      const it = list[i];
      if (row.length === 0 || worst([...row, it], side) <= worst(row, side)) { row.push(it); i++; }
      else flush();
    }
    if (row.length) flush();
  }

  /* ---------------------------------------------------------------- rendering */
  size() {
    const r = this.stage.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    for (const c of [this.base, this.over]) {
      c.width = Math.max(1, Math.round(r.width * dpr));
      c.height = Math.max(1, Math.round(r.height * dpr));
    }
    return { w: r.width, h: r.height, dpr };
  }

  render() {
    if (!this.data) return;
    const { w, h, dpr } = this.size();
    const ctx = this.base.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(document.documentElement);
    this.theme = {
      bg: "rgba(0,0,0,0)",
      solid: css.getPropertyValue("--surface").trim() || "#121527",
      dir: css.getPropertyValue("--surface-2").trim() || "rgba(255,255,255,0.045)",
      border: css.getPropertyValue("--border").trim() || "#222a37",
      text: css.getPropertyValue("--text").trim() || "#e8ebf1",
      text3: css.getPropertyValue("--text-3").trim() || "#6c7688",
    };
    ctx.clearRect(0, 0, w, h);
    this.rects = [];
    this.arcs = [];
    this.bubbles = [];
    if (this.mode === "sunburst") this.drawSunburst(ctx, w, h);
    else if (this.mode === "bubbles") this.drawBubbles(ctx, w, h);
    else this.drawTreemap(ctx, w, h);
    this.drawOver();
  }

  /* dominant category of an expanded folder, from the loaded data */
  domCat(n) {
    if (n._k !== undefined) return n._k;
    if (n.k != null) return (n._k = n.k);
    const sizes = {};
    const walk = (x) => {
      if (x.t === 1 && x.k != null) sizes[x.k] = (sizes[x.k] || 0) + x.s;
      else if (x.t === 0 && !x.c && x.k != null) sizes[x.k] = (sizes[x.k] || 0) + x.s;
      else if (x.t === 2 && x.k != null) sizes[x.k] = (sizes[x.k] || 0) + x.s;
      (x.c || []).forEach(walk);
    };
    walk(n);
    let best = null, bs = 0;
    for (const k in sizes) if (sizes[k] > bs) { bs = sizes[k]; best = +k; }
    return (n._k = best);
  }

  bubbleColor(n) {
    if (this.colorBy === "age") return this.ageColor(n.m);
    if (this.colorBy === "folder" || n.t === 2) return n.t === 2 ? "#4a5262" : `hsl(${this.topHue.get(n) ?? 260} 62% 58%)`;
    const k = n.t === 1 ? n.k : this.domCat(n);
    return k != null ? this.catColor(k) : "#7c6cf0";
  }

  layoutBubbles(W, H) {
    const key = `${W}x${H}`;
    if (this._bub && this._bub.data === this.data && this._bub.key === key) return this._bub.nodes;
    const kids = (this.data.c || []).filter((c) => c.s > 0).sort((a, b) => b.s - a.s).slice(0, 90);
    const total = kids.reduce((a, c) => a + c.s, 0) || 1;
    const scale = Math.sqrt((W * H * 0.5) / (Math.PI * total));
    const nodes = kids.map((c, i) => {
      const r = Math.max(5, scale * Math.sqrt(c.s));
      const a = i * 2.39996, d = 10 * Math.sqrt(i) * (scale / 6 + 1);
      return { n: c, r, x: W / 2 + Math.cos(a) * d, y: H / 2 + Math.sin(a) * d };
    });
    // relax: push overlapping bubbles apart, pull everything gently to the centre
    for (let it = 0; it < 320; it++) {
      const k = 0.02 * (1 - it / 320);
      for (const p of nodes) { p.x += (W / 2 - p.x) * k; p.y += (H / 2 - p.y) * k; }
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const dist = Math.hypot(dx, dy) || 0.01;
          const min = a.r + b.r + 3;
          if (dist < min) {
            const push = (min - dist) / 2, ux = dx / dist, uy = dy / dist;
            const wa = b.r / (a.r + b.r), wb = a.r / (a.r + b.r);
            a.x -= ux * push * wa * 2; a.y -= uy * push * wa * 2;
            b.x += ux * push * wb * 2; b.y += uy * push * wb * 2;
          }
        }
      }
      for (const p of nodes) {
        p.x = Math.max(p.r + 4, Math.min(W - p.r - 4, p.x));
        p.y = Math.max(p.r + 4, Math.min(H - p.r - 4, p.y));
      }
    }
    this._bub = { data: this.data, key, nodes };
    return nodes;
  }

  drawBubbles(ctx, W, H) {
    const nodes = this.layoutBubbles(W, H);
    const font = (wgt, px) => `${wgt} ${px}px "Space Grotesk","Segoe UI",system-ui,sans-serif`;
    for (const b of nodes) {
      const col = this.toHex(this.bubbleColor(b.n));
      // soft glow
      ctx.save();
      ctx.shadowColor = U.hexToRgba(col, 0.45);
      ctx.shadowBlur = Math.min(40, b.r * 0.5);
      const g = ctx.createRadialGradient(b.x - b.r * 0.35, b.y - b.r * 0.4, b.r * 0.1, b.x, b.y, b.r);
      g.addColorStop(0, U.shade(col, 0.45));
      g.addColorStop(0.55, col);
      g.addColorStop(1, U.shade(col, -0.35));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      // inner rings hint at sub-folders
      if (b.n.t === 0 && b.n.c && b.n.c.length && b.r > 30) {
        const sub = b.n.c.filter((x) => x.s > 0).slice(0, 6);
        let off = 0;
        sub.forEach((x, i) => {
          const rr = Math.max(3, b.r * 0.62 * Math.sqrt(x.s / b.n.s));
          const a = i * 2.39996 + 0.6;
          const d = i === 0 ? 0 : b.r * 0.42;
          ctx.beginPath();
          ctx.arc(b.x + Math.cos(a) * d * (i ? 1 : 0), b.y + Math.sin(a) * d * (i ? 1 : 0) + off, Math.min(rr, b.r * 0.38), 0, Math.PI * 2);
          ctx.fillStyle = "rgba(255,255,255,0.08)";
          ctx.fill();
        });
      }
      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(255,255,255,0.22)";
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r - 0.5, 0, Math.PI * 2);
      ctx.stroke();
      if (b.r > 26) {
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        const px = Math.max(10, Math.min(18, b.r / 4.2));
        ctx.font = font(650, px);
        let label = b.n.n;
        const max = b.r * 1.6;
        while (label.length > 3 && ctx.measureText(label).width > max) label = label.slice(0, -2);
        if (label !== b.n.n) label = label.slice(0, -1) + "…";
        ctx.fillStyle = "rgba(8,10,20,0.88)";
        ctx.fillText(label, b.x, b.y - px * 0.45);
        ctx.font = font(500, px * 0.82);
        ctx.fillStyle = "rgba(8,10,20,0.65)";
        ctx.fillText(U.bytes(b.n.s), b.x, b.y + px * 0.7);
        ctx.restore();
      }
      this.bubbles.push(b);
    }
  }

  drawTreemap(ctx, W, H) {
    const font = (wgt, px) => `${wgt} ${px}px "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif`;
    const rects = this.rects;
    const draw = (node, x, y, w, h, depth) => {
      rects.push({ n: node, x, y, w, h, depth });
      const isDir = node.t === 0;
      if (isDir && node.c && node.c.length && w > 6 && h > 6) {
        // frame + header
        ctx.fillStyle = depth % 2 ? this.theme.dir : this.theme.bg;
        if (depth > 0 && ctx.roundRect) {
          ctx.beginPath();
          ctx.roundRect(x + 0.5, y + 0.5, w - 1, h - 1, Math.min(7, w / 6, h / 6));
          ctx.fill();
          ctx.strokeStyle = "rgba(255,255,255,0.06)";
          ctx.lineWidth = 1;
          ctx.stroke();
        } else ctx.fillRect(x, y, w, h);
        let hy = 0;
        if (w > 56 && h > 38 && depth > 0) {
          hy = 18;
          ctx.fillStyle = this.theme.text;
          ctx.font = font(600, 11.5);
          ctx.textBaseline = "middle";
          const label = `${node.n}  ·  ${U.bytes(node.s)}`;
          ctx.save();
          ctx.beginPath(); ctx.rect(x + 4, y, w - 8, hy); ctx.clip();
          ctx.fillText(label, x + 6, y + hy / 2 + 1);
          ctx.restore();
        }
        const pad = depth > 0 ? 2 : 0;
        const out = [];
        SpaceMap.squarify(node.c, x + pad, y + pad + hy, w - pad * 2, h - pad * 2 - hy, out);
        for (const [c, cx, cy, cw, ch] of out) draw(c, cx, cy, cw, ch, depth + 1);
        return;
      }
      // leaf (file / collapsed folder / rest)
      const color = this.fileColor(node);
      if (w >= 4 && h >= 4) {
        const g = ctx.createLinearGradient(x, y, x + w, y + h);
        g.addColorStop(0, U.shade(this.toHex(color), 0.22));
        g.addColorStop(1, U.shade(this.toHex(color), -0.32));
        ctx.fillStyle = g;
      } else ctx.fillStyle = color;
      if (ctx.roundRect && w > 7 && h > 7) {
        ctx.beginPath();
        ctx.roundRect(x + 1, y + 1, w - 2, h - 2, Math.min(5, w / 5, h / 5));
        ctx.fill();
        if (w > 24 && h > 24) { // glossy top highlight
          const hl = ctx.createLinearGradient(x, y, x, y + Math.min(h, 60));
          hl.addColorStop(0, "rgba(255,255,255,0.22)");
          hl.addColorStop(1, "rgba(255,255,255,0)");
          ctx.fillStyle = hl;
          ctx.fill();
        }
      } else ctx.fillRect(x + 0.5, y + 0.5, Math.max(0.5, w - 1), Math.max(0.5, h - 1));
      if (node.t === 2 && w > 8 && h > 8) {
        ctx.save();
        ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
        ctx.strokeStyle = "rgba(255,255,255,0.06)";
        ctx.lineWidth = 1;
        for (let k = -h; k < w; k += 7) { ctx.beginPath(); ctx.moveTo(x + k, y + h); ctx.lineTo(x + k + h, y); ctx.stroke(); }
        ctx.restore();
      }
      if (w > 54 && h > 22) {
        ctx.save();
        ctx.beginPath(); ctx.rect(x + 3, y + 2, w - 6, h - 4); ctx.clip();
        ctx.fillStyle = "rgba(10,12,18,0.82)";
        ctx.font = font(600, 11.5);
        ctx.textBaseline = "top";
        ctx.fillText(node.n, x + 6, y + 5);
        if (h > 38) {
          ctx.font = font(500, 11);
          ctx.fillStyle = "rgba(10,12,18,0.62)";
          ctx.fillText(U.bytes(node.s), x + 6, y + 20);
        }
        ctx.restore();
      }
    };
    draw(this.data, 0, 0, W, H, 0);
  }

  toHex(color) {
    if (color.startsWith("#")) return color;
    const m = color.match(/\d+(\.\d+)?/g);
    if (!m) return "#6b7385";
    if (color.startsWith("hsl")) {
      const [hh, ss, ll] = m.map(Number);
      const s = ss / 100, l = ll / 100;
      const k = (n) => (n + hh / 30) % 12;
      const a = s * Math.min(l, 1 - l);
      const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
      return "#" + [f(0), f(8), f(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join("");
    }
    return "#" + m.slice(0, 3).map((v) => (+v).toString(16).padStart(2, "0")).join("");
  }

  maxDepth(n, d = 0) { if (!n.c || !n.c.length) return d; let m = d; for (const c of n.c) m = Math.max(m, this.maxDepth(c, d + 1)); return m; }

  drawSunburst(ctx, W, H) {
    const cx = W / 2, cy = H / 2;
    const R = Math.min(W, H) / 2 - 12;
    const depth = Math.min(7, Math.max(1, this.maxDepth(this.data)));
    const r0 = Math.max(46, R * 0.17);
    const ring = (R - r0) / depth;
    this.sb = { cx, cy, r0, ring, depth };
    const arcs = this.arcs;
    const walk = (node, a0, a1, d) => {
      if (!node.c || d >= depth) return;
      const total = node.c.reduce((a, c) => a + c.s, 0) || 1;
      let a = a0;
      for (const c of node.c) {
        const span = ((a1 - a0) * c.s) / total;
        if (span > 0.0025) {
          const inner = r0 + d * ring, outer = inner + ring - 1.2;
          let color;
          if (c.t === 0 && this.colorBy === "type") {
            const hue = this.topHue.get(this.topOf(c)) ?? 260;
            color = `hsl(${hue} ${48 - d * 3}% ${Math.min(70, 44 + d * 5)}%)`;
          } else color = this.fileColor(c);
          ctx.beginPath();
          ctx.arc(cx, cy, outer, a, a + span - (span > 0.02 ? 0.004 : 0));
          ctx.arc(cx, cy, inner, a + span - (span > 0.02 ? 0.004 : 0), a, true);
          ctx.closePath();
          ctx.fillStyle = color;
          ctx.fill();
          arcs.push({ n: c, a0: a, a1: a + span, r0: inner, r1: outer, d });
          if (span * (inner + ring / 2) > 70 && ring > 18) {
            ctx.save();
            const mid = a + span / 2;
            ctx.translate(cx + Math.cos(mid) * (inner + ring / 2), cy + Math.sin(mid) * (inner + ring / 2));
            let rot = mid + Math.PI / 2;
            if (Math.sin(mid) > 0) rot += Math.PI;
            ctx.rotate(rot);
            ctx.fillStyle = "rgba(10,12,18,0.85)";
            ctx.font = `600 11px "Segoe UI",system-ui`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const max = span * (inner + ring / 2) - 10;
            let label = c.n;
            while (label.length > 3 && ctx.measureText(label).width > max) label = label.slice(0, -2);
            if (label !== c.n) label = label.slice(0, -1) + "…";
            ctx.fillText(label, 0, 0);
            ctx.restore();
          }
          walk(c, a, a + span, d + 1);
        }
        a += span;
      }
    };
    walk(this.data, -Math.PI / 2, Math.PI * 1.5, 0);
    // centre
    ctx.beginPath();
    ctx.arc(cx, cy, r0 - 4, 0, Math.PI * 2);
    const cg = ctx.createRadialGradient(cx, cy - r0 * 0.4, 2, cx, cy, r0);
    cg.addColorStop(0, "rgba(139,92,246,0.35)");
    cg.addColorStop(1, this.theme.solid);
    ctx.fillStyle = cg;
    ctx.fill();
    ctx.strokeStyle = "rgba(139,92,246,0.45)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = this.theme.text;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `650 17px "Segoe UI Variable Display","Segoe UI",system-ui`;
    ctx.fillText(U.bytes(this.data.s), cx, cy - 6);
    ctx.font = `500 11.5px "Segoe UI",system-ui`;
    ctx.fillStyle = this.theme.text3;
    let name = U.basename(this.data.n) || this.data.n;
    if (name.length > 18) name = name.slice(0, 17) + "…";
    ctx.fillText(name, cx, cy + 14);
  }

  drawOver() {
    const dpr = window.devicePixelRatio || 1;
    const ctx = this.over.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.over.width, this.over.height);
    const h = this.hover;
    if (!h) return;
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#ffffff";
    if (this.mode === "bubbles") {
      ctx.save();
      ctx.shadowColor = "rgba(255,255,255,0.7)";
      ctx.shadowBlur = 18;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(h.x, h.y, h.r + 1, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      ctx.fillStyle = "rgba(255,255,255,0.1)";
      ctx.beginPath();
      ctx.arc(h.x, h.y, h.r, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    if (this.mode === "sunburst") {
      const { cx, cy } = this.sb;
      ctx.beginPath();
      ctx.arc(cx, cy, h.r1, h.a0, h.a1);
      ctx.arc(cx, cy, h.r0, h.a1, h.a0, true);
      ctx.closePath();
      ctx.fillStyle = "rgba(255,255,255,0.16)";
      ctx.fill();
      ctx.stroke();
    } else {
      ctx.fillStyle = "rgba(255,255,255,0.12)";
      ctx.fillRect(h.x, h.y, h.w, h.h);
      ctx.strokeRect(h.x + 1, h.y + 1, h.w - 2, h.h - 2);
      const p = this.rects.find((r) => r.n === h.n._p && r.depth > 0);
      if (p) { ctx.strokeStyle = "rgba(167,139,250,0.9)"; ctx.lineWidth = 1.5; ctx.strokeRect(p.x + 0.75, p.y + 0.75, p.w - 1.5, p.h - 1.5); }
    }
  }

  /* ---------------------------------------------------------------- interaction */
  hit(e) {
    const r = this.over.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    if (this.mode === "bubbles") {
      for (let i = this.bubbles.length - 1; i >= 0; i--) {
        const b = this.bubbles[i];
        if (Math.hypot(x - b.x, y - b.y) <= b.r) return b;
      }
      return null;
    }
    if (this.mode === "sunburst") {
      const { cx, cy, r0 } = this.sb || {};
      const dx = x - cx, dy = y - cy, dist = Math.hypot(dx, dy);
      if (dist < r0) return { center: true };
      let ang = Math.atan2(dy, dx);
      if (ang < -Math.PI / 2) ang += Math.PI * 2;
      for (let i = this.arcs.length - 1; i >= 0; i--) {
        const a = this.arcs[i];
        if (dist >= a.r0 && dist <= a.r1 + 1.2 && ang >= a.a0 && ang <= a.a1) return a;
      }
      return null;
    }
    for (let i = this.rects.length - 1; i >= 0; i--) {
      const q = this.rects[i];
      if (x >= q.x && x < q.x + q.w && y >= q.y && y < q.y + q.h && q.depth > 0) {
        // prefer the leaf; for frames, the header area means the folder itself
        return q;
      }
    }
    return null;
  }

  pathOf(n) {
    const names = [];
    let x = n;
    while (x && x !== this.data) { names.push(x.n); x = x._p; }
    names.reverse();
    if (!this.rootPath) return names.join("\\");
    const base = this.rootPath.endsWith("\\") ? this.rootPath : this.rootPath + "\\";
    return base + names.join("\\");
  }

  describe(hit) {
    const n = hit.n;
    const type = n.t === 0 ? "dir" : n.t === 1 ? "file" : "rest";
    return { type, id: n.i, name: n.n, size: n.s, mtime: n.m, cat: n.k != null ? App.catKeys[n.k] : null, path: type === "rest" ? null : this.pathOf(n), node: n };
  }

  setHover(h) {
    if (h === this.hover) return;
    this.hover = h;
    this.drawOver();
  }

  move(e) {
    const h = this.hit(e);
    if (!h || h.center) {
      this.setHover(null);
      if (h && h.center && this.data._p !== undefined) UI.tip(e, `<b>${U.esc(this.data.n)}</b><div class="tp">Click to go up</div>`);
      else UI.hideTip();
      this.over.style.cursor = h && h.center ? "pointer" : "default";
      return;
    }
    this.setHover(h);
    const d = this.describe(h);
    const pct = this.data.s ? U.pct(d.size / this.data.s) : "";
    let extra = "";
    if (d.type === "file") extra = `${App.catLabel(d.cat)} · modified ${U.ago(d.mtime)}`;
    else if (d.type === "dir") extra = `Folder · last change ${U.ago(d.mtime)} · click to zoom in`;
    else extra = "Many small files and folders grouped together";
    UI.tip(e, `<b>${U.esc(d.name)}</b> — ${U.bytes(d.size)} <span class="muted">(${pct})</span><div class="tp">${U.esc(extra)}</div>${d.path ? `<div class="tp mono">${U.esc(d.path)}</div>` : ""}`);
    this.over.style.cursor = d.type === "dir" ? "zoom-in" : "pointer";
  }

  click(e, dbl) {
    const h = this.hit(e);
    if (!h) return;
    if (h.center) { if (this.opts.onUp) this.opts.onUp(); return; }
    const d = this.describe(h);
    if (d.type === "dir" && d.id != null) { if (this.opts.onOpen) this.opts.onOpen(d.id); }
    else if (d.type === "file") {
      if (dbl && this.opts.onActivate) this.opts.onActivate(d);
      else if (this.opts.onSelect) this.opts.onSelect(d);
    } else if (d.type === "rest" && h.n._p && h.n._p.i != null && h.n._p !== this.data && this.opts.onOpen) {
      this.opts.onOpen(h.n._p.i);
    }
  }
}
