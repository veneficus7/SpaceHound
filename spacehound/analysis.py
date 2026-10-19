"""Read-only queries over a finished ScanTree, shaped for the UI."""

import fnmatch
import heapq
import itertools
import os
import time
from collections import defaultdict

from .categories import CATEGORIES, CATEGORY_KEYS, EXT_TO_CAT, OTHER, cat_of, ext_of
from .scanner import (AGE_LABELS, F_DENIED, F_EXCLUDED, F_HIDDEN, F_LINK, F_REMOVED, F_ROOT, F_SUB_DENIED,
                      F_SUB_LINK, F_SYSTEM, F_VIRTUAL, SIZE_LABELS)
from .util import is_under

DAY = 86400


def node_info(tree, node):
    return {
        "id": node.idx,
        "name": node.name,
        "path": tree.path(node),
        "size": node.size,
        "files": node.nfiles,
        "dirs": node.ndirs,
        "mtime": node.mtime,
        "cloud": node.cloud,
        "flags": node.flags,
        "parent": node.parent.idx if node.parent is not None else None,
    }


def crumbs(tree, node):
    out = []
    n = node
    while n is not None:
        out.append({"id": n.idx, "name": n.name})
        n = n.parent
    return list(reversed(out))


def _dir_item(node, parent_size):
    return {
        "type": "dir", "id": node.idx, "name": node.name, "size": node.size, "files": node.nfiles,
        "dirs": node.ndirs, "mtime": node.mtime, "flags": node.flags, "cloud": node.cloud,
        "pct": node.size / parent_size if parent_size else 0,
    }


def children(tree, node_id, sort="size", desc=True, limit=3000):
    with tree.lock:
        node = tree.get(node_id) or tree.root
        base = tree.path(node)
        items = [_dir_item(d, node.size) for d in node.dirs if not d.flags & F_REMOVED]
        for name, size, mtime in node.files:
            items.append({
                "type": "file", "name": name, "size": size, "mtime": mtime,
                "path": (base + name if base.endswith(os.sep) else base + os.sep + name) if base else name,
                "cat": CATEGORY_KEYS[cat_of(name)], "pct": size / node.size if node.size else 0,
            })
        if node.small_n:
            items.append({"type": "small", "name": f"{node.small_n:,} smaller files", "size": node.small_size,
                          "files": node.small_n, "mtime": 0, "pct": node.small_size / node.size if node.size else 0})
        keyf = {
            "name": lambda x: (x["type"] == "small", x["name"].lower()),
            "files": lambda x: x.get("files", 1),
            "mtime": lambda x: x.get("mtime", 0),
            "type": lambda x: (x["type"], x.get("cat", "")),
        }.get(sort, lambda x: x["size"])
        items.sort(key=keyf, reverse=desc if sort != "name" else not desc)
        return {
            "node": node_info(tree, node),
            "crumbs": crumbs(tree, node),
            "items": items[:limit],
            "total_items": len(items),
        }


def list_small_files(tree, node_id):
    """Live listing of the files below the storage threshold for one folder."""
    node = tree.get(node_id)
    if node is None:
        return []
    path = tree.path(node)
    out = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_file(follow_symlinks=False):
                        st = e.stat(follow_symlinks=False)
                        if st.st_size < tree.threshold:
                            out.append({"type": "file", "name": e.name, "size": st.st_size, "mtime": int(st.st_mtime),
                                        "path": e.path, "cat": CATEGORY_KEYS[cat_of(e.name)]})
                except OSError:
                    continue
    except OSError:
        pass
    out.sort(key=lambda x: -x["size"])
    return out


def _add_cat_sizes(tree, node, sizes, limit=40000):
    seen = 0
    for d in tree.iter_dirs(node):
        for name, size, _ in d.files:
            sizes[EXT_TO_CAT.get(ext_of(name), OTHER)] += size
            seen += 1
        if seen > limit:
            break


def _argmax(sizes):
    best = max(range(len(sizes)), key=lambda i: sizes[i])
    return best if sizes[best] > 0 else None


def _dominant_category(tree, node):
    """Category holding most bytes inside a folder (used to colour collapsed folders)."""
    sizes = [0] * len(CATEGORIES)
    _add_cat_sizes(tree, node, sizes)
    return _argmax(sizes)


def treemap(tree, node_id, max_depth=12, budget=6000, min_frac=0.00015):
    with tree.lock:
        node = tree.get(node_id) or tree.root
        min_size = max(1, int(node.size * min_frac))
        root_out = {"i": node.idx, "n": node.name, "s": node.size, "t": 0, "m": node.mtime, "c": []}
        counter = itertools.count()
        heap = [(-node.size, next(counter), node, root_out, 0)]
        count = 1
        collapsed = []
        while heap:
            _, _, n, out, depth = heapq.heappop(heap)
            if count >= budget:
                # out of budget: this folder stays a solid block
                out.pop("c", None)
                collapsed.append((n, out))
                continue
            kids = out["c"]
            other = 0
            other_n = 0
            other_cats = [0] * len(CATEGORIES)
            for d in n.dirs:
                if d.flags & F_REMOVED or d.size <= 0:
                    continue
                if d.size < min_size or count >= budget:
                    other += d.size
                    other_n += 1
                    _add_cat_sizes(tree, d, other_cats, limit=4000)
                    continue
                child = {"i": d.idx, "n": d.name, "s": d.size, "t": 0, "m": d.mtime}
                kids.append(child)
                count += 1
                if (d.dirs or d.files) and depth + 1 < max_depth:
                    child["c"] = []
                    heapq.heappush(heap, (-d.size, next(counter), d, child, depth + 1))
                else:
                    collapsed.append((d, child))
            for name, size, mtime in n.files:
                cat = EXT_TO_CAT.get(ext_of(name), OTHER)
                if size < min_size or count >= budget:
                    other += size
                    other_n += 1
                    other_cats[cat] += size
                    continue
                kids.append({"n": name, "s": size, "t": 1, "k": cat, "m": mtime})
                count += 1
            other += n.small_size
            other_n += n.small_n
            if other > 0:
                rest = {"n": f"{other_n:,} smaller items", "s": other, "t": 2}
                k = _argmax(other_cats)
                # colour the block when one type clearly dominates what's inside it
                if k is not None and other_cats[k] > other * 0.5:
                    rest["k"] = k
                kids.append(rest)
        for d, out in collapsed:
            k = _dominant_category(tree, d)
            if k is not None:
                out["k"] = k
        return {"root": root_out, "crumbs": crumbs(tree, node), "path": tree.path(node), "count": count}


def breakdown(tree, node_id=None):
    """Bytes per category inside a folder (files >= threshold, rest as 'small')."""
    with tree.lock:
        node = tree.get(node_id) or tree.root
        if node is tree.root:
            return type_stats(tree)["categories"]
        sizes = [0] * len(CATEGORIES)
        counts = [0] * len(CATEGORIES)
        small = 0
        small_n = 0
        for d in tree.iter_dirs(node):
            small += d.small_size
            small_n += d.small_n
            for name, size, _ in d.files:
                c = EXT_TO_CAT.get(ext_of(name), OTHER)
                sizes[c] += size
                counts[c] += 1
        out = [{"key": k, "label": l, "color": col, "size": sizes[i], "count": counts[i]}
               for i, (k, l, col) in enumerate(CATEGORIES) if sizes[i]]
        if small:
            out.append({"key": "small", "label": "Small files", "color": "#4b5563", "size": small, "count": small_n})
        out.sort(key=lambda x: -x["size"])
        return out


def type_stats(tree, node_id=None):
    with tree.lock:
        node = tree.get(node_id) if node_id is not None else None
        if node is None or node is tree.root:
            ext_items = [(ext, c, s) for ext, (c, s) in tree.ext_stats.items() if c > 0]
        else:
            agg = defaultdict(lambda: [0, 0])
            small = [0, 0]
            for d in tree.iter_dirs(node):
                small[0] += d.small_n
                small[1] += d.small_size
                for name, size, _ in d.files:
                    a = agg[ext_of(name)]
                    a[0] += 1
                    a[1] += size
            ext_items = [(ext, c, s) for ext, (c, s) in agg.items()]
            if small[0]:
                ext_items.append(("(small files)", small[0], small[1]))
        cats = [[0, 0] for _ in CATEGORIES]
        exts = []
        for ext, c, s in ext_items:
            ci = EXT_TO_CAT.get(ext, OTHER)
            cats[ci][0] += c
            cats[ci][1] += s
            exts.append({"ext": ext or "(none)", "count": c, "size": s, "cat": CATEGORY_KEYS[ci]})
        exts.sort(key=lambda x: -x["size"])
        categories = [{"key": k, "label": l, "color": col, "size": cats[i][1], "count": cats[i][0]}
                      for i, (k, l, col) in enumerate(CATEGORIES) if cats[i][0]]
        categories.sort(key=lambda x: -x["size"])
        return {"categories": categories, "exts": exts[:400], "ext_count": len(exts)}


def _in_scope(tree, opts):
    node = tree.get(opts.get("node_id")) if opts.get("node_id") is not None else None
    return node or tree.root


def largest_files(tree, opts):
    """Biggest files, with optional filters. opts keys:
    node_id, cats[list], exts[list], min_size, older_days, newer_days, query, limit, offset."""
    limit = min(int(opts.get("limit") or 500), 5000)
    offset = int(opts.get("offset") or 0)
    cats = {CATEGORY_KEYS.index(c) for c in opts.get("cats") or [] if c in CATEGORY_KEYS} or None
    exts = {e.lower().lstrip(".") for e in opts.get("exts") or []} or None
    min_size = int(opts.get("min_size") or 0)
    now = time.time()
    older = now - float(opts["older_days"]) * DAY if opts.get("older_days") else None
    newer = now - float(opts["newer_days"]) * DAY if opts.get("newer_days") else None
    query = (opts.get("query") or "").strip().lower()
    pattern = query if any(ch in query for ch in "*?[") else None
    want = limit + offset
    heap = []
    total_n = 0
    total_size = 0
    with tree.lock:
        start = _in_scope(tree, opts)
        counter = itertools.count()
        for d in tree.iter_dirs(start):
            files = d.files
            if not files:
                continue
            if files[0][1] < min_size:
                continue
            dpath = None
            for name, size, mtime in files:
                if size < min_size:
                    break  # sorted largest first
                if older is not None and mtime > older:
                    continue
                if newer is not None and mtime < newer:
                    continue
                if cats is not None or exts is not None:
                    ext = ext_of(name)
                    if exts is not None and ext not in exts:
                        continue
                    if cats is not None and EXT_TO_CAT.get(ext, OTHER) not in cats:
                        continue
                if query:
                    low = name.lower()
                    if pattern:
                        if not fnmatch.fnmatchcase(low, pattern):
                            continue
                    elif query not in low:
                        if dpath is None:
                            dpath = tree.path(d).lower()
                        if query not in dpath:
                            continue
                total_n += 1
                total_size += size
                item = (size, next(counter), d, name, mtime)
                if len(heap) < want:
                    heapq.heappush(heap, item)
                elif size > heap[0][0]:
                    heapq.heapreplace(heap, item)
        rows = sorted(heap, key=lambda x: (-x[0], x[1]))[offset:offset + limit]
        out = []
        for size, _, d, name, mtime in rows:
            folder = tree.path(d)
            out.append({"type": "file", "name": name, "size": size, "mtime": mtime, "folder": folder,
                        "folder_id": d.idx, "path": folder + name if folder.endswith(os.sep) else folder + os.sep + name,
                        "cat": CATEGORY_KEYS[cat_of(name)]})
    return {"items": out, "matched": total_n, "matched_size": total_size, "threshold": tree.threshold}


def age_histogram(tree, node_id=None):
    with tree.lock:
        node = tree.get(node_id) if node_id is not None else None
        if node is None or node is tree.root:
            return [{"label": AGE_LABELS[i], "count": c, "size": s} for i, (c, s) in enumerate(tree.age_hist)]
        edges = [30, 182, 365, 730, 1825]
        now = time.time()
        times = sorted(now - d * DAY for d in edges)
        from bisect import bisect_right
        hist = [[0, 0] for _ in AGE_LABELS]
        for d in tree.iter_dirs(node):
            for _, size, mtime in d.files:
                b = 5 - bisect_right(times, mtime)
                hist[b][0] += 1
                hist[b][1] += size
        return [{"label": AGE_LABELS[i], "count": c, "size": s} for i, (c, s) in enumerate(hist)]


def size_histogram(tree):
    return [{"label": SIZE_LABELS[i], "count": c, "size": s} for i, (c, s) in enumerate(tree.size_hist)]


SYSTEM_TOP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin",
              "system volume information", "recovery", "$winreagent", "boot"}


def _is_system_branch(tree, node):
    n = node
    while n is not None and not n.flags & F_ROOT:
        if n.parent is not None and n.parent.flags & F_ROOT and n.name.lower() in SYSTEM_TOP:
            return True
        if n.name.lower() == "appdata":
            return True
        n = n.parent
    return False


def stale_folders(tree, opts):
    """Big folders where nothing changed for a long time (top-most only)."""
    days = float(opts.get("days") or 365)
    min_size = int(opts.get("min_size") or (500 << 20))
    include_system = bool(opts.get("include_system"))
    cutoff = time.time() - days * DAY
    out = []
    with tree.lock:
        start = _in_scope(tree, opts)
        stack = [start]
        while stack:
            n = stack.pop()
            for c in n.dirs:
                if c.flags & (F_REMOVED | F_LINK) or c.size < min_size:
                    continue
                if not include_system and n.flags & F_ROOT and c.name.lower() in SYSTEM_TOP:
                    continue
                if not include_system and c.name.lower() == "appdata":
                    continue
                if 0 < c.mtime < cutoff:
                    item = _dir_item(c, 0)
                    item["path"] = tree.path(c)
                    item["idle_days"] = int((time.time() - c.mtime) / DAY)
                    out.append(item)
                else:
                    stack.append(c)
    out.sort(key=lambda x: -x["size"])
    return {"items": out[:1000], "total": sum(x["size"] for x in out)}


def empty_folders(tree, opts):
    """Folders with no files at all below them (top-most only)."""
    include_hidden = bool(opts.get("include_hidden"))
    out = []
    blocked = F_DENIED | F_SUB_DENIED | F_LINK | F_SUB_LINK | F_EXCLUDED | F_REMOVED
    with tree.lock:
        start = _in_scope(tree, opts)
        stack = [start]
        while stack:
            n = stack.pop()
            for c in n.dirs:
                if c.flags & F_REMOVED:
                    continue
                if n.flags & F_ROOT and c.name.lower() in SYSTEM_TOP:
                    continue
                if c.name.lower() in ("appdata", ".git"):
                    continue
                if not include_hidden and c.flags & (F_HIDDEN | F_SYSTEM):
                    continue
                if c.nfiles == 0 and c.cloud == 0 and c.size == 0 and not c.flags & blocked:
                    out.append({"id": c.idx, "name": c.name, "path": tree.path(c), "dirs": c.ndirs, "mtime": c.mtime})
                elif c.nfiles > 0 or c.dirs:
                    stack.append(c)
    out.sort(key=lambda x: x["path"].lower())
    return {"items": out[:5000], "count": len(out)}


def search(tree, query, limit=300):
    query = (query or "").strip().lower()
    if not query:
        return {"items": []}
    pattern = query if any(ch in query for ch in "*?[") else None

    def hit(name):
        low = name.lower()
        return fnmatch.fnmatchcase(low, pattern) if pattern else query in low

    heap = []
    counter = itertools.count()
    with tree.lock:
        for d in tree.iter_dirs():
            if d.flags & F_VIRTUAL:
                continue
            if hit(d.name):
                item = (d.size, next(counter), "dir", d, None)
                if len(heap) < limit:
                    heapq.heappush(heap, item)
                elif d.size > heap[0][0]:
                    heapq.heapreplace(heap, item)
            for f in d.files:
                if hit(f[0]):
                    item = (f[1], next(counter), "file", d, f)
                    if len(heap) < limit:
                        heapq.heappush(heap, item)
                    elif f[1] > heap[0][0]:
                        heapq.heapreplace(heap, item)
        out = []
        for size, _, kind, d, f in sorted(heap, key=lambda x: -x[0]):
            if kind == "dir":
                item = _dir_item(d, 0)
                item["path"] = tree.path(d)
            else:
                folder = tree.path(d)
                item = {"type": "file", "name": f[0], "size": f[1], "mtime": f[2], "folder_id": d.idx,
                        "path": folder + f[0] if folder.endswith(os.sep) else folder + os.sep + f[0],
                        "cat": CATEGORY_KEYS[cat_of(f[0])]}
            out.append(item)
    return {"items": out}


def possible_duplicates(tree, min_size=10 << 20):
    """Cheap estimate: same-size big files (a real check happens in the duplicate finder)."""
    groups = defaultdict(int)
    for _, (name, size, _) in tree.iter_files():
        if size >= min_size:
            groups[size] += 1
    waste = sum(size * (n - 1) for size, n in groups.items() if n > 1)
    count = sum(1 for n in groups.values() if n > 1)
    return waste, count


def top_dirs(tree, node, n=10):
    with tree.lock:
        dirs = [d for d in node.dirs if not d.flags & F_REMOVED][:n]
        out = []
        for d in dirs:
            item = _dir_item(d, node.size)
            item["path"] = tree.path(d)
            out.append(item)
        return out


def old_size_under(tree, node, days):
    cutoff = time.time() - days * DAY
    total = 0
    for d in tree.iter_dirs(node):
        for _, size, mtime in d.files:
            if mtime < cutoff:
                total += size
    return total


def deep_biggest(tree, n=12):
    """The most specific big folders: large, and not just a container of one bigger child."""
    out = []
    with tree.lock:
        total = tree.root.size or 1
        stack = [tree.root]
        while stack:
            node = stack.pop()
            for c in node.dirs:
                if c.flags & F_REMOVED or c.size < total * 0.01:
                    continue
                biggest_child = c.dirs[0].size if c.dirs else 0
                if biggest_child < c.size * 0.6:
                    item = _dir_item(c, total)
                    item["path"] = tree.path(c)
                    out.append(item)
                stack.append(c)
    out.sort(key=lambda x: -x["size"])
    return out[:n]
