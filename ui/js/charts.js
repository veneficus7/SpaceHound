/* Small dependency-free SVG/HTML charts. Each returns markup; hover info
   is carried in data-tip attributes and shown by the global tooltip. */

const Charts = (() => {
  function arc(cx, cy, r0, r1, a0, a1) {
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const [x0, y0] = p(r1, a0), [x1, y1] = p(r1, a1), [x2, y2] = p(r0, a1), [x3, y3] = p(r0, a0);
    return `M${x0},${y0} A${r1},${r1} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${r0},${r0} 0 ${large} 0 ${x3},${y3} Z`;
  }

  /* segments: [{label, value, color, key}] */
  function donut(segments, { size = 190, thickness = 26, center = "", sub = "" } = {}) {
    const total = segments.reduce((a, s) => a + s.value, 0) || 1;
    const r1 = size / 2 - 2, r0 = r1 - thickness, c = size / 2;
    let a = -Math.PI / 2;
    const gap = segments.length > 1 ? 0.012 : 0;
    const paths = segments.map((s) => {
      const span = (s.value / total) * Math.PI * 2;
      if (span <= 0) return "";
      const a0 = a + gap / 2, a1 = Math.max(a0 + 0.001, a + span - gap / 2);
      a += span;
      const tip = `<b>${U.esc(s.label)}</b><div class="tp">${U.bytes(s.value)} · ${U.pct(s.value / total)}</div>`;
      if (span >= Math.PI * 2 - 0.001) {
        return `<circle cx="${c}" cy="${c}" r="${(r0 + r1) / 2}" fill="none" stroke="${s.color}" stroke-width="${thickness}" data-tip="${U.esc(tip)}" data-key="${U.esc(s.key || "")}"/>`;
      }
      return `<path d="${arc(c, c, r0, r1, a0, a1)}" fill="${s.color}" data-tip="${U.esc(tip)}" data-key="${U.esc(s.key || "")}"/>`;
    }).join("");
    return `<svg class="donut" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      ${paths}
      <text x="${c}" y="${c - 2}" text-anchor="middle" style="font:650 19px var(--font-display);fill:var(--text)">${U.esc(center)}</text>
      <text x="${c}" y="${c + 17}" text-anchor="middle" style="font-size:11.5px;fill:var(--text-3)">${U.esc(sub)}</text>
    </svg>`;
  }

  /* items: [{label, value, color?, sub?}] -> vertical columns */
  function columns(items, { height = 170, fmt = U.bytes, color = "var(--accent)" } = {}) {
    const max = Math.max(1, ...items.map((i) => i.value));
    const w = 100 / items.length;
    const uid = "cg" + Math.random().toString(36).slice(2, 7);
    const defs = items.map((it, i) => `<linearGradient id="${uid}${i}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${it.color || color}" stop-opacity="1"/><stop offset="1" stop-color="${it.color || color}" stop-opacity="0.25"/></linearGradient>`).join("");
    const cols = items.map((it, i) => {
      const h = Math.max(it.value > 0 ? 2 : 0, (it.value / max) * (height - 46));
      const tip = `<b>${U.esc(it.label)}</b><div class="tp">${fmt(it.value)}${it.sub ? " · " + U.esc(it.sub) : ""}</div>`;
      return `<g data-tip="${U.esc(tip)}">
        <rect x="${i * w + w * 0.2}%" y="${height - 26 - h}" width="${w * 0.6}%" height="${h}" rx="8" fill="url(#${uid}${i})" style="filter:drop-shadow(0 0 10px ${it.color || "rgba(139,92,246,.5)"}55)"/>
        <text x="${i * w + w / 2}%" y="${height - 31 - h}" text-anchor="middle" style="font-size:11px;fill:var(--text-2);font-weight:600">${it.value ? fmt(it.value) : ""}</text>
        <text x="${i * w + w / 2}%" y="${height - 8}" text-anchor="middle">${U.esc(it.label)}</text>
      </g>`;
    }).join("");
    return `<svg class="chart-svg" width="100%" height="${height}"><defs>${defs}</defs>${cols}</svg>`;
  }

  /* segments: [{label, value, color}] across a total (remaining = empty) */
  function stackbar(segments, total) {
    total = total || segments.reduce((a, s) => a + s.value, 0) || 1;
    const parts = segments.filter((s) => s.value > 0).map((s) => {
      const tip = `<b>${U.esc(s.label)}</b><div class="tp">${U.bytes(s.value)} · ${U.pct(s.value / total)}</div>`;
      const bg = s.pattern ? `repeating-linear-gradient(45deg, ${s.color}, ${s.color} 5px, transparent 5px, transparent 9px)` : s.color;
      return `<i style="width:${(s.value / total) * 100}%;background:${bg}" data-tip="${U.esc(tip)}"></i>`;
    }).join("");
    const legend = segments.filter((s) => s.value > 0).map((s) =>
      `<span><i style="background:${s.color}"></i>${U.esc(s.label)} <b>${U.bytes(s.value)}</b></span>`).join("");
    return `<div class="stackbar">${parts}</div><div class="legend">${legend}</div>`;
  }

  /* points: [{t, v}] - sparkline / area chart */
  function area(points, { height = 160, color = "#8b5cf6" } = {}) {
    if (points.length < 2) return `<div class="muted small" style="padding:30px 0;text-align:center">Scan again later to see a trend line.</div>`;
    const W = 1000, H = height, pad = 26;
    const t0 = points[0].t, t1 = points[points.length - 1].t || t0 + 1;
    const vs = points.map((p) => p.v);
    let lo = Math.min(...vs), hi = Math.max(...vs);
    if (hi - lo < hi * 0.02) { lo -= hi * 0.01; hi += hi * 0.01; }
    const x = (t) => pad + ((t - t0) / (t1 - t0 || 1)) * (W - pad * 2);
    const y = (v) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - pad * 2);
    const line = points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    const fill = `${line} L${x(t1)},${H - pad} L${x(t0)},${H - pad} Z`;
    const dots = points.map((p) => `<circle cx="${x(p.t)}" cy="${y(p.v)}" r="4.5" fill="${color}" stroke="var(--surface)" stroke-width="2"
       data-tip="${U.esc(`<b>${U.bytes(p.v)}</b><div class="tp">${U.dateTime(p.t)}</div>`)}"/>`).join("");
    return `<svg class="chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" width="100%" height="${H}">
      <defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".35"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
      <path d="${fill}" fill="url(#ag)"/><path d="${line}" fill="none" stroke="${color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
      ${dots}
      <text x="${pad}" y="14">${U.bytes(hi)}</text><text x="${pad}" y="${H - 6}">${U.bytes(lo)}</text>
    </svg>`;
  }

  /* gauge ring for a drive */
  function ring(frac, { size = 64, stroke = 7, color } = {}) {
    const r = (size - stroke) / 2, c = size / 2, len = 2 * Math.PI * r;
    const col = color || U.usageColor(frac);
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="${stroke}"/>
      <circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${col}" stroke-width="${stroke}" stroke-linecap="round"
        stroke-dasharray="${len * Math.min(1, frac)} ${len}" transform="rotate(-90 ${c} ${c})"/>
      <text x="${c}" y="${c + Math.max(9, Math.round(size * 0.24)) * 0.36}" text-anchor="middle" style="font:650 ${Math.max(9, Math.round(size * 0.24))}px var(--font-display);fill:var(--text)">${Math.round(frac * 100)}%</text>
    </svg>`;
  }

  return { donut, columns, stackbar, area, ring };
})();
