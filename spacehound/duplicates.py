"""Duplicate file finder.

Pipeline (each stage only looks at what survived the previous one):
1. group candidate files by exact size,
2. hash the first and last 64 KB (files <= 128 KB are fully covered here),
3. hash the whole file with BLAKE2b,
4. drop paths that are already hard links to the same data.
"""

import hashlib
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .categories import CATEGORY_KEYS, cat_of
from .fsops import walk_files
from .util import is_under, maybe_long

CHUNK = 64 * 1024
BLOCK = 1024 * 1024


def _partial_hash(path, size):
    h = hashlib.blake2b(digest_size=16)
    with open(maybe_long(path), "rb", buffering=0) as fh:
        h.update(fh.read(CHUNK))
        if size > 2 * CHUNK:
            fh.seek(size - CHUNK)
            h.update(fh.read(CHUNK))
        elif size > CHUNK:
            h.update(fh.read())
    return h.digest()


def _full_hash(path, job):
    h = hashlib.blake2b(digest_size=20)
    with open(maybe_long(path), "rb") as fh:
        while True:
            if job.cancelled:
                return None
            block = fh.read(BLOCK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def collect_candidates(job, tree, roots, min_size, max_size, cats, exclude):
    """[(path, size, mtime)] for every file in scope."""
    cat_ids = {CATEGORY_KEYS.index(c) for c in cats} if cats else None
    out = []

    def keep(path, size):
        if size < min_size or (max_size and size > max_size):
            return False
        if cat_ids is not None and cat_of(path) not in cat_ids:
            return False
        for ex in exclude:
            if is_under(path, ex):
                return False
        return True

    use_tree = tree is not None and min_size >= tree.threshold and all(tree.covers(r) for r in roots)
    if use_tree:
        job.update(phase="collect", detail="Using scan results")
        for r in roots:
            node = tree.find_dir(r)
            if node is None:
                continue
            for d, (name, size, mtime) in tree.iter_files(node):
                path = tree.file_path(d, name)
                if keep(path, size):
                    out.append((path, size, mtime))
    else:
        for r in roots:
            count = 0
            for path, size, mtime in walk_files(r, job=job):
                count += 1
                if count % 2000 == 0:
                    job.update(phase="collect", detail=path, files=count)
                if keep(path, size):
                    out.append((path, size, mtime))
    return out


def find_duplicates(job, tree, roots, min_size=1 << 20, max_size=0, cats=None, exclude=(), threads=6):
    t0 = time.time()
    files = collect_candidates(job, tree, roots, min_size, max_size, cats, list(exclude))
    job.check()

    by_size = defaultdict(list)
    for f in files:
        by_size[f[1]].append(f)
    stage1 = [g for g in by_size.values() if len(g) > 1]
    n1 = sum(len(g) for g in stage1)
    job.update(phase="partial", total=n1, done=0, candidates=len(files))

    pool = ThreadPoolExecutor(max_workers=max(1, threads))
    try:
        # ---- stage 2: head + tail hash
        flat = [f for g in stage1 for f in g]
        done = 0
        partial = {}

        def ph(f):
            try:
                return f, _partial_hash(f[0], f[1])
            except OSError:
                return f, None

        for f, digest in pool.map(ph, flat):
            done += 1
            if digest is not None:
                partial.setdefault((f[1], digest), []).append(f)
            if done % 200 == 0:
                job.check()
                job.update(done=done)
        stage2 = [g for g in partial.values() if len(g) > 1]
        job.check()

        # ---- stage 3: full hash (only needed above 128 KB)
        need_full = [g for g in stage2 if g[0][1] > 2 * CHUNK]
        final = [(g, None) for g in stage2 if g[0][1] <= 2 * CHUNK]
        total_bytes = sum(f[1] for g in need_full for f in g)
        job.update(phase="full", total=sum(len(g) for g in need_full), done=0, bytes_total=total_bytes, bytes_done=0)
        flat = [f for g in need_full for f in g]
        progress = {"done": 0, "bytes": 0}

        def fh(f):
            try:
                return f, _full_hash(f[0], job)
            except OSError:
                return f, None

        full = {}
        for f, digest in pool.map(fh, flat):
            progress["done"] += 1
            progress["bytes"] += f[1]
            if digest is not None:
                full.setdefault((f[1], digest), []).append(f)
            if progress["done"] % 20 == 0:
                job.check()
                job.update(done=progress["done"], bytes_done=progress["bytes"])
        job.check()
        for (size, digest), g in full.items():
            if len(g) > 1:
                final.append((g, digest))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    # ---- stage 4: hard-link awareness + result shaping
    job.update(phase="finishing")
    groups = []
    for g, digest in final:
        seen = set()
        entries = []
        for path, size, mtime in g:
            try:
                st = os.stat(maybe_long(path))
                ino = (st.st_dev, st.st_ino)
            except OSError:
                continue
            linked = ino in seen
            seen.add(ino)
            entries.append({"path": path, "mtime": mtime, "linked": linked, "ino": f"{ino[0]}:{ino[1]}"})
        unique = len(seen)
        if unique < 2:
            continue
        size = g[0][1]
        entries.sort(key=lambda e: e["path"].lower())
        groups.append({
            "size": size,
            "hash": digest or "small-file",
            "wasted": size * (unique - 1),
            "count": len(entries),
            "cat": CATEGORY_KEYS[cat_of(entries[0]["path"])],
            "files": entries,
        })
    groups.sort(key=lambda x: x["wasted"], reverse=True)
    for i, grp in enumerate(groups):
        grp["id"] = i
    return {
        "groups": groups,
        "wasted": sum(x["wasted"] for x in groups),
        "files": sum(x["count"] for x in groups),
        "candidates": len(files),
        "roots": list(roots),
        "min_size": min_size,
        "elapsed": time.time() - t0,
    }
