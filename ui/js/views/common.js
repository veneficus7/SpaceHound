/* Reusable file/folder table with selection, sorting and row actions. */

const FileTable = {
  /* opts: {max, showType=true, showFolder=true, emptyText, sortable=true, extraCol:{label, width, render}} */
  mount(container, items, sel, opts = {}) {
    const state = { items: items.slice(), key: opts.sortKey || null, desc: true };
    const max = opts.max || Math.max(1, ...items.map((i) => i.size || 0));
    const showType = opts.showType !== false;
    const extra = opts.extraCol;

    const sortBy = (key) => {
      if (state.key === key) state.desc = !state.desc; else { state.key = key; state.desc = key !== "name"; }
      const f = {
        name: (x) => (x.name || "").toLowerCase(),
        size: (x) => x.size || 0,
        mtime: (x) => x.mtime || 0,
        type: (x) => x.cat || (x.type === "dir" ? "~dir" : ""),
        extra: (x) => (extra && extra.sortValue ? extra.sortValue(x) : 0),
      }[key];
      state.items.sort((a, b) => {
        const va = f(a), vb = f(b);
        const r = va < vb ? -1 : va > vb ? 1 : 0;
        return state.desc ? -r : r;
      });
      draw();
    };

    const row = (it, i) => {
      const isDir = it.type === "dir";
      const sub = opts.showFolder !== false ? (it.folder || U.dirname(it.path)) : "";
      return `<tr data-i="${i}" class="${sel.has(it) ? "sel" : ""}">
        <td class="w-check"><input type="checkbox" class="check" data-ck ${sel.has(it) ? "checked" : ""}></td>
        <td><div class="name-cell">${isDir ? R.dirIcon() : R.fileIcon(it.cat)}<div class="txt"><div class="nm" title="${U.esc(it.name)}">${U.esc(it.name)}</div>
          ${sub ? `<div class="pth" title="${U.esc(it.path)}">‎${U.esc(sub)}‎</div>` : ""}</div></div></td>
        ${showType ? `<td>${isDir ? `<span class="badge accent">Folder</span>` : R.catBadge(it.cat)}</td>` : ""}
        ${extra ? `<td class="${extra.cls || ""}">${extra.render(it)}</td>` : ""}
        <td><div class="size-cell">${R.sizeBar((it.size || 0) / max, isDir ? null : (App.cats[it.cat] || {}).color)}<b class="num" style="width:74px;text-align:right">${U.bytes(it.size)}</b></div></td>
        <td title="${U.esc(U.dateTime(it.mtime))}" class="text-2">${it.mtime ? U.ago(it.mtime) : "—"}</td>
        <td><div class="row-actions">
          <button class="btn ghost sm icon" data-act="reveal" title="Show in File Explorer">${icon("folder", "sm")}</button>
          <button class="btn ghost sm icon" data-act="menu" title="More">${icon("more", "sm")}</button></div></td>
      </tr>`;
    };

    const th = (key, label, cls = "") => `<th class="${cls} ${opts.sortable !== false ? "sortable" : ""} ${state.key === key ? "sorted" : ""}" data-sort="${key}">${label}${state.key === key ? (state.desc ? " ↓" : " ↑") : ""}</th>`;

    const draw = () => {
      if (!state.items.length) {
        container.innerHTML = R.empty("check", opts.emptyTitle || "Nothing here", opts.emptyText || "No files match.");
        return;
      }
      const allSel = state.items.every((it) => sel.has(it));
      container.innerHTML = `<div class="card table-wrap"><table class="t">
        <colgroup><col style="width:44px"><col>${showType ? '<col style="width:150px">' : ""}${extra ? `<col style="width:${extra.width || 130}px">` : ""}<col style="width:230px"><col style="width:120px"><col style="width:84px"></colgroup>
        <thead><tr><th class="w-check"><input type="checkbox" class="check" data-all ${allSel ? "checked" : ""}></th>
          ${th("name", "Name")}${showType ? th("type", "Type") : ""}${extra ? th("extra", extra.label) : ""}${th("size", "Size")}${th("mtime", "Modified")}<th></th></tr></thead>
        <tbody>${state.items.map(row).join("")}</tbody></table></div>`;
    };

    container.onclick = (e) => {
      const sortTh = e.target.closest("th[data-sort]");
      if (sortTh && opts.sortable !== false) { sortBy(sortTh.dataset.sort); return; }
      if (e.target.matches("[data-all]")) {
        if (e.target.checked) state.items.forEach((it) => sel.map.set(sel.key(it), it));
        else state.items.forEach((it) => sel.map.delete(sel.key(it)));
        sel.changed();
        draw();
        return;
      }
      const tr = e.target.closest("tr[data-i]");
      if (!tr) return;
      const it = state.items[+tr.dataset.i];
      const act = e.target.closest("[data-act]");
      if (act) {
        if (act.dataset.act === "reveal") Actions.reveal(it.path);
        else Actions.itemMenu(e, it, opts.menuExtra ? opts.menuExtra(it) : []);
        return;
      }
      sel.toggle(it);
      tr.classList.toggle("sel", sel.has(it));
      tr.querySelector("[data-ck]").checked = sel.has(it);
      if (opts.onFocus) opts.onFocus(it);
    };
    container.ondblclick = (e) => {
      const tr = e.target.closest("tr[data-i]");
      if (!tr || e.target.closest("[data-act], input")) return;
      const it = state.items[+tr.dataset.i];
      if (it.type === "dir" && it.id != null) App.go("explorer", { node: it.id });
      else Actions.reveal(it.path);
    };
    container.oncontextmenu = (e) => {
      const tr = e.target.closest("tr[data-i]");
      if (!tr) return;
      const it = state.items[+tr.dataset.i];
      Actions.itemMenu(e, it, opts.menuExtra ? opts.menuExtra(it) : []);
    };
    draw();
    return { redraw: draw, state };
  },
};

function selButtons(sel, source) {
  return [
    { label: "Move to…", icon: "move", onClick: () => Actions.move(sel.items) },
    { label: "Recycle Bin", icon: "trash", onClick: () => Actions.delete(sel.items, { mode: "recycle", source }) },
    { label: "Delete permanently", icon: "trash-x", kind: "danger", onClick: () => Actions.delete(sel.items, { mode: "permanent", source }) },
  ];
}

/* render a page-level job progress block and resolve with the job result */
async function inlineJob(container, jobId, { title, describe }) {
  container.innerHTML = `<div class="card pad fade-in" style="max-width:640px;margin:40px auto">
    <div class="row"><div class="spinner"></div><b>${U.esc(title)}</b><div class="spacer"></div>
      <button class="btn sm" data-cancel>${icon("stop", "sm")}Stop</button></div>
    <div class="progress" style="margin:14px 0 10px"><i style="width:0%"></i></div>
    <div class="small text-2 jd ellipsis">Starting…</div></div>`;
  container.querySelector("[data-cancel]").onclick = () => API.cancel_job(jobId);
  return waitJob(jobId, (st) => {
    const p = st.progress || {};
    let frac = null;
    if (p.total) frac = (p.done || 0) / p.total;
    if (p.bytes_total) frac = (p.bytes_done || 0) / p.bytes_total;
    const bar = container.querySelector(".progress > i");
    const jd = container.querySelector(".jd");
    if (!bar) return;
    if (frac == null) { bar.parentElement.classList.add("indeterminate"); }
    else { bar.parentElement.classList.remove("indeterminate"); bar.style.width = Math.min(100, frac * 100) + "%"; }
    jd.innerHTML = describe ? describe(p, st) : U.esc(p.current || p.phase || "Working…");
  });
}
