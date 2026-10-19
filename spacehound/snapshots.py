"""Scan snapshots: remember folder sizes after every scan and diff them later.

This answers "my disk was fine last month - what grew?".
"""

import gzip
import json
import os
import time

from .scanner import F_REMOVED, F_VIRTUAL
from .util import data_dir, norm

MAX_ENTRIES = 40000
MIN_SIZE = 5 << 20
MAX_DEPTH = 10


def _dir():
    path = os.path.join(data_dir(), "snapshots")
    os.makedirs(path, exist_ok=True)
    return path


def _key(paths):
    return "|".join(sorted(norm(p) for p in paths))


def capture(tree):
    """Folder sizes worth remembering: big enough and not too deep."""
    sizes = {}
    stack = [(tree.root, 0)]
    while stack:
        node, depth = stack.pop()
        if node.flags & F_REMOVED:
            continue
        if not node.flags & F_VIRTUAL:
            sizes[tree.path(node)] = node.size
        if depth < MAX_DEPTH:
            for child in node.dirs:
                if child.size >= MIN_SIZE:
                    stack.append((child, depth + 1))
    if len(sizes) > MAX_ENTRIES:
        keep = sorted(sizes.items(), key=lambda kv: -kv[1])[:MAX_ENTRIES]
        sizes = dict(keep)
    return sizes


def save(tree, keep=30):
    snap = {
        "id": time.strftime("%Y%m%d-%H%M%S"),
        "time": time.time(),
        "roots": tree.paths,
        "key": _key(tree.paths),
        "total": tree.root.size,
        "files": tree.root.nfiles,
        "usage": tree.drive_usage,
        "sizes": capture(tree),
    }
    path = os.path.join(_dir(), f"{snap['id']}.json.gz")
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, separators=(",", ":"))
    meta = {k: snap[k] for k in META_KEYS}
    with open(os.path.join(_dir(), f"{snap['id']}.meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    # retention per scanned root set
    same = [s for s in list_snapshots() if s["key"] == snap["key"]]
    for old in same[keep:]:
        delete(old["id"])
    return snap["id"]


META_KEYS = ("id", "time", "roots", "key", "total", "files", "usage")


def _load(snap_id):
    safe = os.path.basename(str(snap_id))
    with gzip.open(os.path.join(_dir(), f"{safe}.json.gz"), "rt", encoding="utf-8") as fh:
        return json.load(fh)


def list_snapshots():
    out = []
    folder = _dir()
    for name in os.listdir(folder):
        if not name.endswith(".meta.json"):
            continue
        try:
            with open(os.path.join(folder, name), "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            continue
        if os.path.exists(os.path.join(folder, f"{meta.get('id')}.json.gz")):
            out.append(meta)
    out.sort(key=lambda s: -s["time"])
    return out


def delete(snap_id):
    ok = False
    safe = os.path.basename(str(snap_id))
    for suffix in (".json.gz", ".meta.json"):
        try:
            os.remove(os.path.join(_dir(), safe + suffix))
            ok = True
        except OSError:
            pass
    return ok


def compare(old_sizes, new_sizes, roots, min_delta=50 << 20, limit=300):
    """Return the most specific folders that grew or shrank.

    A folder is "specific" when none of its children explains most (>=70%) of
    its change - so we report ``Downloads\\Movies`` rather than every parent.
    """
    deltas = {}
    lower_old = {norm(k): v for k, v in old_sizes.items()}
    lower_new = {norm(k): (k, v) for k, v in new_sizes.items()}
    names = {}
    for nk, (k, v) in lower_new.items():
        deltas[nk] = v - lower_old.get(nk, 0)
        names[nk] = k
    for nk, v in lower_old.items():
        if nk not in lower_new:
            deltas[nk] = -v
            names[nk] = next((k for k in old_sizes if norm(k) == nk), nk)

    children = {}
    for nk in deltas:
        parent = os.path.dirname(nk)
        if parent != nk:
            children.setdefault(parent, []).append(nk)

    root_keys = {norm(r) for r in roots}
    specific = []
    for nk, d in deltas.items():
        if abs(d) < min_delta:
            continue
        explained = False
        for c in children.get(nk, ()):
            cd = deltas[c]
            if (cd > 0) == (d > 0) and abs(cd) >= 0.7 * abs(d):
                explained = True
                break
        if not explained:
            specific.append({
                "path": names[nk], "delta": d,
                "old": lower_old.get(nk, 0), "new": lower_new.get(nk, ("", 0))[1],
                "is_new": nk not in lower_old, "is_gone": nk not in lower_new, "is_root": nk in root_keys,
            })
    specific.sort(key=lambda x: -abs(x["delta"]))
    return specific[:limit]


def compare_with_tree(tree, snap_id):
    snap = _load(snap_id)
    current = capture(tree)
    changes = compare(snap["sizes"], current, tree.paths)
    total_old = snap.get("total", 0)
    return {
        "snapshot": {k: snap.get(k) for k in ("id", "time", "roots", "total", "files", "usage")},
        "total_delta": tree.root.size - total_old,
        "grew": [c for c in changes if c["delta"] > 0],
        "shrank": [c for c in changes if c["delta"] < 0],
    }


def previous_for(tree):
    """The most recent snapshot of the same roots taken before this scan."""
    key = _key(tree.paths)
    for s in list_snapshots():
        if s["key"] == key and s["time"] < (tree.started or time.time()) - 1:
            return s
    return None


def history(paths):
    key = _key(paths)
    return [s for s in list_snapshots() if s["key"] == key]
