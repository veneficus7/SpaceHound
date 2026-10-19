/* Formatting & DOM helpers (globals on purpose: no bundler needed). */

const U = (() => {
  const UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

  function bytes(n, digits) {
    n = Number(n) || 0;
    const neg = n < 0;
    n = Math.abs(n);
    let i = 0;
    while (n >= 1024 && i < UNITS.length - 1) { n /= 1024; i++; }
    const d = digits != null ? digits : (i === 0 ? 0 : n >= 100 ? 0 : n >= 10 ? 1 : 2);
    return (neg ? "−" : "") + n.toFixed(d) + " " + UNITS[i];
  }

  function bytesParts(n) {
    const s = bytes(n);
    const k = s.lastIndexOf(" ");
    return [s.slice(0, k), s.slice(k + 1)];
  }

  const num = (n) => (Number(n) || 0).toLocaleString("en-US");
  const pct = (p, d = 1) => (p * 100).toFixed(p > 0 && p < 0.001 ? 2 : d) + "%";

  function date(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function dateTime(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function ago(ts) {
    if (!ts) return "never";
    const s = Date.now() / 1000 - ts;
    if (s < 60) return "just now";
    const m = s / 60, h = m / 60, d = h / 24, mo = d / 30.44, y = d / 365.25;
    if (m < 60) return `${Math.floor(m)} min ago`;
    if (h < 24) return `${Math.floor(h)} h ago`;
    if (d < 31) return `${Math.floor(d)} day${Math.floor(d) === 1 ? "" : "s"} ago`;
    if (mo < 12) return `${Math.floor(mo)} month${Math.floor(mo) === 1 ? "" : "s"} ago`;
    return `${y.toFixed(y < 2 ? 1 : 0)} years ago`;
  }

  function duration(sec) {
    if (sec < 1) return `${Math.round(sec * 1000)} ms`;
    if (sec < 60) return `${sec.toFixed(1)} s`;
    const m = Math.floor(sec / 60);
    return `${m} min ${Math.round(sec % 60)} s`;
  }

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function basename(p) {
    const s = String(p || "").replace(/[\\/]+$/, "");
    const i = Math.max(s.lastIndexOf("\\"), s.lastIndexOf("/"));
    return i >= 0 ? s.slice(i + 1) || s : s;
  }

  function dirname(p) {
    const s = String(p || "").replace(/[\\/]+$/, "");
    const i = Math.max(s.lastIndexOf("\\"), s.lastIndexOf("/"));
    return i > 0 ? s.slice(0, i) : s;
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  function $(sel, root = document) { return root.querySelector(sel); }
  function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  function html(strings, ...vals) {
    // tagged template: values are escaped unless wrapped with U.raw()
    let out = strings[0];
    vals.forEach((v, i) => {
      if (v && v.__raw) out += v.s;
      else if (Array.isArray(v)) out += v.map((x) => (x && x.__raw ? x.s : esc(x))).join("");
      else out += esc(v);
      out += strings[i + 1];
    });
    return { __raw: true, s: out, toString() { return out; } };
  }
  const raw = (s) => ({ __raw: true, s: String(s ?? ""), toString() { return this.s; } });

  function el(markup) {
    const t = document.createElement("template");
    t.innerHTML = String(markup).trim();
    return t.content.firstElementChild;
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function hexToRgba(hex, a) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  function shade(hex, f) {
    const h = hex.replace("#", "");
    const n = parseInt(h, 16);
    let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    if (f >= 0) { r += (255 - r) * f; g += (255 - g) * f; b += (255 - b) * f; }
    else { r *= 1 + f; g *= 1 + f; b *= 1 + f; }
    return `rgb(${r | 0}, ${g | 0}, ${b | 0})`;
  }

  function usageColor(p) {
    if (p >= 0.9) return "var(--bad)";
    if (p >= 0.75) return "var(--warn)";
    return "var(--accent)";
  }

  return { bytes, bytesParts, num, pct, date, dateTime, ago, duration, esc, basename, dirname, debounce, $, $$, html, raw, el, sleep, hexToRgba, shade, usageColor };
})();
