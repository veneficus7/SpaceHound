"""Turn a scan into plain-language findings: "why is my disk full?"."""

import os
import time

from . import analysis, devjunk, winapi
from .categories import CATEGORIES, CATEGORY_KEYS
from .scanner import F_ROOT
from .util import fmt_size, norm

GB = 1 << 30


def _pct(part, whole):
    return f"{part / whole * 100:.0f}%" if whole else "0%"


def health(tree, metrics, usage=None):
    """A 0-100 disk health score from free space, reclaimable junk and stale data."""
    usages = [u for u in (tree.drive_usage or {}).values() if u] or ([usage] if usage else [])
    if not usages:
        return None
    total = sum(u["total"] for u in usages)
    free = sum(u["free"] for u in usages)
    used = max(1, total - free)
    free_ratio = free / total if total else 0
    junk = sum(metrics.get(k, 0) for k in ("cache", "recycle", "dups", "dev"))
    old = metrics.get("old", 0)
    s_free = min(1.0, free_ratio / 0.25) * 55
    s_junk = (1 - min(1.0, junk / used * 4)) * 30
    s_old = (1 - min(1.0, old / max(1, tree.root.size) * 2)) * 15
    score = int(round(s_free + s_junk + s_old))
    label, tone = ((("Healthy", "good") if score >= 80 else ("Fair", "info") if score >= 60
                    else ("Needs attention", "warn") if score >= 40 else ("Critical", "bad")))
    return {
        "score": score, "label": label, "tone": tone, "total": total, "free": free, "used": total - free,
        "reclaimable": junk,
        "parts": [
            {"key": "free", "label": "Free space", "score": round(s_free), "max": 55,
             "detail": f"{free_ratio * 100:.0f}% of the drive is free"},
            {"key": "junk", "label": "Junk & duplicates", "score": round(s_junk), "max": 30,
             "detail": f"{fmt_size(junk)} could be reclaimed"},
            {"key": "old", "label": "Stale data", "score": round(s_old), "max": 15,
             "detail": f"{fmt_size(old)} untouched for 2+ years"},
        ],
    }


def build(tree, previous=None, recycle=None, metrics=None):
    out = []
    total = tree.root.size or 1
    metrics = metrics if metrics is not None else {}
    if recycle:
        metrics["recycle"] = recycle[0]

    def add(kind, tone, title, text, size=0, action=None, icon=None):
        out.append({"kind": kind, "tone": tone, "title": title, "text": text, "size": size,
                    "action": action, "icon": icon or kind})

    def safe(fn):
        try:
            fn()
        except Exception as exc:  # an insight must never break the overview
            print("insight failed:", fn.__name__, exc)

    def growth():
        if not previous:
            return
        delta = total - (previous.get("total") or 0)
        days = max(0.0, (time.time() - previous["time"]) / 86400)
        when = "today" if days < 1 else f"{days:.0f} day{'s' if days >= 2 else ''} ago"
        if abs(delta) >= 256 << 20:
            add("growth", "warn" if delta > 0 else "good",
                f"{'+' if delta > 0 else '−'}{fmt_size(abs(delta))} since your last scan",
                f"Compared with the scan from {when}. See exactly which folders changed.",
                abs(delta), {"view": "history"}, "trend")

    def unaccounted():
        for root, usage in tree.drive_usage.items():
            node = tree.find_dir(root)
            if node is None:
                continue
            hidden = usage["used"] - node.size
            if hidden > 4 * GB and hidden > usage["used"] * 0.04:
                add("hidden", "warn", f"{fmt_size(hidden)} on {root} is not visible to a normal scan",
                    "Usually System Restore points / shadow copies, the NTFS file table, or folders that need "
                    "admin rights. Run SpaceHound as administrator for a fuller picture, and check System "
                    "Protection settings.", hidden, {"open": "ms-settings:storagesense"}, "eye-off")

    def denied():
        if tree.denied_count and not winapi.is_admin():
            add("denied", "info", f"{tree.denied_count:,} folders could not be read",
                "Their size is missing from the results. Restart as administrator to include them.",
                0, {"elevate": True}, "lock")

    def known():
        folders = winapi.known_folders()
        for label in ("Downloads", "Desktop", "Videos", "Documents", "Pictures"):
            path = folders.get(label)
            if not path:
                continue
            node = tree.find_dir(path)
            if node is None or node.size < 2 * GB:
                continue
            old = analysis.old_size_under(tree, node, 180)
            text = f"{_pct(node.size, total)} of everything scanned."
            if old > GB:
                text += f" {fmt_size(old)} of it hasn't been touched in 6+ months."
            tone = "warn" if label in ("Downloads", "Desktop") else "info"
            add("folder", tone, f"{label} holds {fmt_size(node.size)}", text, node.size,
                {"view": "explorer", "node": node.idx}, "folder")

    def recycle_bin():
        if recycle and recycle[0] > GB:
            add("recycle", "warn", f"Recycle Bin: {fmt_size(recycle[0])}",
                f"{recycle[1]:,} deleted items (on all drives) still occupy disk space until the bin is emptied.",
                recycle[0], {"view": "cleanup"}, "trash")

    def categories():
        cats = analysis.type_stats(tree)["categories"]
        cache = next((c for c in cats if c["key"] == "cache"), None)
        metrics["cache"] = cache["size"] if cache else 0
        if cache and cache["size"] > 3 * GB:
            add("cache", "warn", f"{fmt_size(cache['size'])} of caches & temporary files",
                "Render caches, shader caches, download caches and temp files. Most of it can be cleared safely "
                "with Smart Cleanup.", cache["size"], {"view": "largest", "cats": ["cache"]}, "sparkles")
        for c in [c for c in cats if c["key"] not in ("other", "cache")][:2]:
            if c["size"] > total * 0.2 and c["size"] > 10 * GB:
                add("category", "info", f"{c['label']}: {fmt_size(c['size'])}",
                    f"{_pct(c['size'], total)} of the scanned space, in {c['count']:,} files.",
                    c["size"], {"view": "largest", "cats": [c["key"]]}, "pie")

    def dups():
        waste, groups = analysis.possible_duplicates(tree)
        metrics["dups"] = waste
        if waste > GB:
            add("dups", "warn", f"Up to {fmt_size(waste)} may be duplicates",
                f"{groups:,} groups of large files share exactly the same size. Run the duplicate finder to confirm.",
                waste, {"view": "duplicates"}, "copy")

    def dev():
        res = devjunk.find_artifacts(tree, min_size=10 << 20)
        metrics["dev"] = res["total"]
        if res["total"] > GB:
            idle = [p for p in res["projects"] if (p.get("idle_days") or 0) > 90]
            idle_size = sum(p["size"] for p in idle)
            text = f"node_modules, build folders, caches… in {len(res['projects'])} projects."
            if idle_size > 256 << 20:
                text += f" {fmt_size(idle_size)} belongs to projects untouched for 3+ months."
            add("dev", "warn", f"{fmt_size(res['total'])} of rebuildable project files", text,
                res["total"], {"view": "devjunk"}, "code")

    def old_big():
        res = analysis.largest_files(tree, {"older_days": 730, "min_size": 100 << 20, "limit": 1})
        metrics["old"] = res["matched_size"]
        if res["matched_size"] > 5 * GB:
            add("old", "info", f"{fmt_size(res['matched_size'])} in big files untouched for 2+ years",
                f"{res['matched']:,} files over 100 MB nobody has modified since "
                f"{time.strftime('%Y', time.localtime(time.time() - 730 * 86400))}.",
                res["matched_size"], {"view": "old"}, "clock")

    def installers():
        downloads = winapi.known_folder("Downloads")
        node = tree.find_dir(downloads) if downloads else None
        if node is None:
            return
        res = analysis.largest_files(tree, {"node_id": node.idx, "cats": ["app", "diskimage", "archive"], "limit": 1})
        if res["matched_size"] > 2 * GB:
            add("installers", "warn", f"{fmt_size(res['matched_size'])} of installers & archives in Downloads",
                f"{res['matched']:,} .exe / .msi / .iso / .zip files - usually safe to remove once installed or extracted.",
                res["matched_size"], {"view": "largest", "node": node.idx, "cats": ["app", "diskimage", "archive"]},
                "package")

    def special():
        for r in tree.roots:
            if not r.flags & F_ROOT or len(r.name) > 3:
                continue
            for name, size, _ in r.files:
                low = name.lower()
                if low == "hiberfil.sys" and size > 2 * GB:
                    add("hiberfil", "info", f"Hibernation file: {fmt_size(size)}",
                        "If you never hibernate, `powercfg /h off` (admin terminal) gives this space back.",
                        size, {"view": "cleanup"}, "moon")
                elif low == "pagefile.sys" and size > 8 * GB:
                    add("pagefile", "info", f"Page file: {fmt_size(size)}",
                        "Virtual memory managed by Windows. It can be resized in System > About > Advanced settings.",
                        size, None, "cpu")

    def android():
        home = os.path.expanduser("~")
        avd = tree.find_dir(os.path.join(home, ".android", "avd"))
        sdk = tree.find_dir(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk"))
        gradle = tree.find_dir(os.path.join(home, ".gradle"))
        parts = []
        size = 0
        for label, node in (("emulators", avd), ("Android SDK", sdk), ("Gradle", gradle)):
            if node is not None and node.size > GB:
                parts.append(f"{label} {fmt_size(node.size)}")
                size += node.size
        if size > 5 * GB:
            add("android", "info", f"Android tooling uses {fmt_size(size)}", ", ".join(parts) +
                ". Old emulators, system images and Gradle caches are common space hogs.", size,
                {"view": "cleanup"}, "android")

    def cloud():
        if tree.root.cloud > GB:
            add("cloud", "good", f"{fmt_size(tree.root.cloud)} is online-only",
                "OneDrive / cloud placeholder files - they show up in Explorer but use no local disk space.",
                tree.root.cloud, None, "cloud")

    for fn in (growth, unaccounted, recycle_bin, known, dups, dev, installers, categories, old_big,
               special, android, cloud, denied):
        safe(fn)
    order = {"bad": 0, "warn": 1, "info": 2, "good": 3}
    out.sort(key=lambda x: (order.get(x["tone"], 2), -x["size"]))
    return out
