"""The API object exposed to the web UI (via pywebview or the HTTP bridge).

Only public methods are callable from JavaScript. All state lives in
underscore attributes so pywebview does not try to expose it.
"""

import base64
import csv
import html
import io
import os
import subprocess
import sys
import threading
import time

from . import __version__, analysis, cleanup, devjunk, duplicates, fsops, insights, safety, snapshots, winapi
from .categories import category_table
from .jobs import JobManager
from .scanner import F_REMOVED, ScanTree, finalize, scan
from .util import data_dir, fmt_size, is_under, norm, read_json, write_json

DEFAULT_SETTINGS = {
    "theme": "dark",
    "delete_mode": "recycle",
    "threads": max(4, min(16, (os.cpu_count() or 8))),
    "threshold_kb": 64,
    "excluded": [],
    "protected": [],
    "snapshot_keep": 30,
    "dup_min_mb": 1,
    "dup_skip_system": True,
    "confirm_permanent": True,
}

IMAGE_TYPES = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp", "bmp": "bmp", "ico": "x-icon",
               "avif": "avif", "svg": "svg+xml"}


class Api:
    def __init__(self, mode="webview", start_paths=None):
        self._mode = mode
        self._start_paths = start_paths
        self._window = None
        self._jobs = JobManager()
        self._tree = None
        self._insights = None
        self._insights_dirty = True
        self._health = None
        self._previous = None
        self._dups = None
        self._cleanup = None
        self._apps = None
        self._lock = threading.RLock()
        self._settings_path = os.path.join(data_dir(), "settings.json")
        self._activity_path = os.path.join(data_dir(), "activity.json")
        self._settings = dict(DEFAULT_SETTINGS)
        self._settings.update(read_json(self._settings_path, {}))
        self._activity = read_json(self._activity_path, {"entries": [], "freed": 0})
        self._app_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
        safety.set_user_protected(self._settings.get("protected"))

    # ------------------------------------------------------------------ helpers
    def _set_window(self, window):
        self._window = window

    def _require_tree(self):
        if self._tree is None:
            raise RuntimeError("No scan results yet - run a scan first")
        return self._tree

    def _log(self, action, items, freed, mode="", errors=0, extra=None):
        entry = {"time": time.time(), "action": action, "items": items, "freed": freed, "mode": mode, "errors": errors}
        if extra:
            entry.update(extra)
        with self._lock:
            self._activity["entries"].insert(0, entry)
            del self._activity["entries"][500:]
            if mode != "recycle":
                self._activity["freed"] = self._activity.get("freed", 0) + freed
            write_json(self._activity_path, self._activity)

    def _system_excludes(self):
        win = os.environ.get("SystemRoot", r"C:\Windows")
        out = [win, os.environ.get("ProgramFiles", r"C:\Program Files"),
               os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
               os.environ.get("ProgramData", r"C:\ProgramData"), os.path.join(os.path.expanduser("~"), "AppData")]
        for d in winapi.list_drives():
            out.append(os.path.join(d["path"], "$Recycle.Bin"))
            out.append(os.path.join(d["path"], "System Volume Information"))
        return out

    # ------------------------------------------------------------------ app
    def app_info(self):
        return {
            "version": __version__,
            "admin": winapi.is_admin(),
            "mode": self._mode,
            "platform": sys.platform,
            "home": os.path.expanduser("~"),
            "cpu": os.cpu_count(),
            "settings": self._settings,
            "categories": category_table(),
            "known": winapi.known_folders(),
            "has_scan": self._tree is not None,
            "data_dir": data_dir(),
            "freed_total": self._activity.get("freed", 0),
            "start_paths": self._take_start_paths(),
            "install": self.install_status(),
        }

    def _take_start_paths(self):
        paths, self._start_paths = self._start_paths, None  # only once
        return paths

    def list_drives(self):
        drives = winapi.list_drives()
        for d in drives:
            if d["ready"]:
                d["recycle"] = winapi.recycle_bin_info(d["path"])[0]
        return drives

    def get_settings(self):
        return self._settings

    def save_settings(self, values):
        clean = dict(self._settings)
        for k, v in (values or {}).items():
            if k in DEFAULT_SETTINGS:
                clean[k] = v
        clean["threads"] = max(1, min(64, int(clean.get("threads") or 8)))
        clean["threshold_kb"] = max(4, min(4096, int(clean.get("threshold_kb") or 64)))
        clean["excluded"] = [p for p in clean.get("excluded") or [] if isinstance(p, str) and p.strip()]
        clean["protected"] = [p for p in clean.get("protected") or [] if isinstance(p, str) and p.strip()]
        self._settings = clean
        safety.set_user_protected(clean["protected"])
        write_json(self._settings_path, clean)
        return clean

    def pick_folder(self):
        if self._window is None:
            return None
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        res = self._window.create_file_dialog(kind)
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res

    def elevate(self):
        if winapi.relaunch_as_admin():
            self._jobs.cancel_all()
            if self._window is not None:
                threading.Timer(0.3, self._window.destroy).start()
            else:
                threading.Timer(0.5, lambda: os._exit(0)).start()
            return True
        return False

    # ------------------------------------------------------------------ install
    def install_status(self):
        from . import installer
        return installer.status()

    def install_app(self, desktop=False):
        from . import installer
        return installer.install(bool(desktop))

    def uninstall_app(self):
        from . import installer
        res = installer.uninstall()
        if self._window is not None and not res["installed"] and installer.current_exe() and \
                norm(installer.current_exe()) == norm(installer.INSTALLED_EXE):
            threading.Timer(0.8, self._window.destroy).start()  # the installed copy removes itself on exit
        return res

    def launch_installed(self):
        """Open the installed copy and close this (portable) window."""
        from . import installer
        if not os.path.exists(installer.INSTALLED_EXE):
            return False
        subprocess.Popen([installer.INSTALLED_EXE], close_fds=True)
        if self._window is not None:
            threading.Timer(0.6, self._window.destroy).start()
        return True

    def reveal(self, path):
        winapi.reveal(path)
        return True

    def open_path(self, path):
        winapi.open_path(path)
        return True

    def open_external(self, target):
        target = str(target)
        if target.startswith(("ms-settings:", "https://")):
            winapi.shell_open(target)
            return True
        return False

    def copy_text(self, text):
        return winapi.set_clipboard(str(text))

    def check_paths(self, paths):
        return safety.summarize(paths, self._app_dir)

    # ------------------------------------------------------------------ jobs
    def job(self, job_id):
        job = self._jobs.get(job_id)
        return job.status() if job else None

    def cancel_job(self, job_id):
        job = self._jobs.get(job_id)
        if job:
            job.cancel()
        return True

    def running_jobs(self):
        return [j.status(include_result=False) for j in self._jobs.running()]

    # ------------------------------------------------------------------ scanning
    def start_scan(self, paths):
        if isinstance(paths, str):
            paths = [paths]
        paths = [p for p in paths if p]
        if not paths:
            raise ValueError("Nothing to scan")
        for j in self._jobs.running("scan"):
            j.cancel()
        job = self._jobs.start("scan", self._do_scan, paths)
        return job.id

    def _do_scan(self, job, paths):
        s = self._settings
        tree = scan(job, paths, threads=int(s["threads"]), threshold=int(s["threshold_kb"]) * 1024,
                    excluded=s.get("excluded") or [])
        job.update(phase="insights")
        previous = None
        try:
            previous = snapshots.previous_for(tree)
            snapshots.save(tree, keep=int(s.get("snapshot_keep") or 30))
        except Exception as exc:
            print("snapshot failed:", exc)
        with self._lock:
            self._tree = tree
            self._previous = previous
            self._dups = None
            self._insights = None
            self._insights_dirty = True
        self._compute_insights()
        return {"ok": True, "files": tree.root.nfiles, "size": tree.root.size}

    def _compute_insights(self):
        tree = self._tree
        if tree is None:
            return []
        recycle = winapi.recycle_bin_info()
        metrics = {}
        res = insights.build(tree, self._previous, recycle, metrics)
        usage = None
        if not tree.drive_usage and tree.paths:
            usage = winapi.disk_usage(os.path.splitdrive(tree.paths[0])[0] + os.sep)
        score = insights.health(tree, metrics, usage)
        with self._lock:
            self._insights = res
            self._health = score
            self._insights_dirty = False
        return res

    def scan_summary(self):
        tree = self._tree
        if tree is None:
            return None
        if self._insights_dirty or self._insights is None:
            self._compute_insights()
        root = tree.root
        if len(tree.roots) == 1:
            top = analysis.top_dirs(tree, root, 12)
        else:
            top = [analysis.node_info(tree, r) | {"pct": r.size / (root.size or 1), "type": "dir"} for r in tree.roots]
        return {
            "roots": tree.paths,
            "root_id": root.idx,
            "size": root.size,
            "files": root.nfiles,
            "dirs": root.ndirs,
            "cloud": root.cloud,
            "duration": (tree.finished or time.time()) - tree.started,
            "finished": tree.finished,
            "denied": tree.denied_count,
            "denied_paths": tree.denied[:100],
            "usage": tree.drive_usage,
            "categories": analysis.type_stats(tree)["categories"],
            "age": analysis.age_histogram(tree),
            "sizes": analysis.size_histogram(tree),
            "top_dirs": top,
            "deep": analysis.deep_biggest(tree, 10),
            "top_files": analysis.largest_files(tree, {"limit": 10})["items"],
            "insights": self._insights or [],
            "health": getattr(self, "_health", None),
            "previous": self._previous,
            "threshold": tree.threshold,
            "admin": winapi.is_admin(),
        }

    def refresh_folder(self, node_id):
        """Rescan one folder in place and graft the result into the tree."""
        tree = self._require_tree()
        node = tree.get(node_id)
        if node is None:
            raise ValueError("Folder no longer exists in the scan")
        job = self._jobs.start("refresh", self._do_refresh, tree.path(node))
        return job.id

    def _do_refresh(self, job, path):
        self._graft(job, path)
        return {"ok": True}

    def _graft(self, job, path):
        tree = self._tree
        if tree is None:
            return
        node = tree.find_dir(path)
        if node is None:
            return
        s = self._settings
        if not os.path.isdir(path):
            tree.remove_path(path)
            return
        sub = scan(job, [path], threads=int(s["threads"]), threshold=tree.threshold, excluded=s.get("excluded") or [])
        new = sub.root
        with tree.lock:
            for d in tree.iter_dirs(node):
                if d is not node:
                    d.flags |= F_REMOVED
            dsize, dfiles, ddirs, dcloud = (new.size - node.size, new.nfiles - node.nfiles,
                                            new.ndirs - node.ndirs, new.cloud - node.cloud)
            node.dirs = new.dirs
            for c in node.dirs:
                c.parent = node
            for attr in ("files", "own_size", "small_n", "small_size", "size", "nfiles", "ndirs", "mtime",
                         "own_mtime", "cloud"):
                setattr(node, attr, getattr(new, attr))
            for n in sub.nodes[1:]:
                n.idx = len(tree.nodes)
                tree.nodes.append(n)
            p = node.parent
            while p is not None:
                p.size += dsize
                p.nfiles += dfiles
                p.ndirs += ddirs
                p.cloud += dcloud
                p = p.parent
            self._insights_dirty = True

    # ------------------------------------------------------------------ browsing
    def children(self, node_id=None, sort="size", desc=True):
        return analysis.children(self._require_tree(), node_id, sort, desc)

    def small_files(self, node_id):
        return analysis.list_small_files(self._require_tree(), node_id)

    def treemap(self, node_id=None, depth=7, budget=5000):
        return analysis.treemap(self._require_tree(), node_id, int(depth), int(budget))

    def breakdown(self, node_id=None):
        return analysis.breakdown(self._require_tree(), node_id)

    def node_details(self, node_id):
        tree = self._require_tree()
        node = tree.get(node_id)
        if node is None:
            return None
        info = analysis.node_info(tree, node)
        info["breakdown"] = analysis.breakdown(tree, node_id)
        info["age"] = analysis.age_histogram(tree, node_id)
        info["top_files"] = analysis.largest_files(tree, {"node_id": node_id, "limit": 8})["items"]
        info["safety"] = safety.classify(info["path"], self._app_dir) if info["path"] else ("blocked", "")
        return info

    def find_node(self, path):
        tree = self._require_tree()
        node = tree.find_dir(path)
        return node.idx if node is not None else None

    def largest(self, opts=None):
        return analysis.largest_files(self._require_tree(), opts or {})

    def types(self, node_id=None):
        return analysis.type_stats(self._require_tree(), node_id)

    def age(self, node_id=None):
        return analysis.age_histogram(self._require_tree(), node_id)

    def stale(self, opts=None):
        return analysis.stale_folders(self._require_tree(), opts or {})

    def empty(self, opts=None):
        return analysis.empty_folders(self._require_tree(), opts or {})

    def search(self, query, limit=300):
        return analysis.search(self._require_tree(), query, int(limit))

    def dev_artifacts(self, opts=None):
        opts = opts or {}
        tree = self._require_tree()
        start = tree.get(opts.get("node_id")) if opts.get("node_id") is not None else None
        return devjunk.find_artifacts(tree, start, int(opts.get("min_size") or (1 << 20)))

    # ------------------------------------------------------------------ duplicates
    def start_duplicates(self, opts=None):
        opts = opts or {}
        tree = self._tree
        roots = opts.get("roots") or (tree.paths if tree else [])
        if not roots:
            raise ValueError("Choose a folder or run a scan first")
        exclude = list(self._settings.get("excluded") or [])
        if opts.get("skip_system", True):
            exclude += self._system_excludes()
        # a folder the user picked explicitly is never excluded by the defaults
        exclude = [e for e in exclude if not any(is_under(r, e) for r in roots)]
        job = self._jobs.start(
            "dups", self._do_dups, tree, roots,
            int(float(opts.get("min_mb") or 1) * (1 << 20)),
            int(float(opts.get("max_mb") or 0) * (1 << 20)),
            opts.get("cats") or None, exclude)
        return job.id

    def _do_dups(self, job, tree, roots, min_size, max_size, cats, exclude):
        res = duplicates.find_duplicates(job, tree, roots, min_size, max_size, cats, exclude,
                                         threads=min(8, int(self._settings["threads"])))
        self._dups = res
        return {"groups": len(res["groups"]), "wasted": res["wasted"]}

    def duplicates_result(self):
        return self._dups

    def _recount_dups(self):
        """Recompute counts/waste after files were deleted or hard-linked."""
        groups = []
        for g in self._dups["groups"]:
            g["count"] = len(g["files"])
            g["wasted"] = g["size"] * (len({f["ino"] for f in g["files"]}) - 1)
            if g["count"] > 1 and g["wasted"] > 0:
                groups.append(g)
        groups.sort(key=lambda x: x["wasted"], reverse=True)
        for i, g in enumerate(groups):
            g["id"] = i
        self._dups["groups"] = groups
        self._dups["wasted"] = sum(g["wasted"] for g in groups)
        self._dups["files"] = sum(g["count"] for g in groups)

    def image_preview(self, path, max_bytes=12 << 20):
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        mime = IMAGE_TYPES.get(ext)
        if not mime:
            return None
        try:
            if os.path.getsize(path) > max_bytes:
                return None
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return None
        return f"data:image/{mime};base64," + base64.b64encode(data).decode("ascii")

    # ------------------------------------------------------------------ cleanup
    def start_cleanup_scan(self):
        job = self._jobs.start("cleanup_scan", self._do_cleanup_scan)
        return job.id

    def _do_cleanup_scan(self, job):
        res = cleanup.scan_rules(job, winapi.is_admin())
        self._cleanup = res
        return res

    def start_cleanup(self, rule_ids):
        job = self._jobs.start("cleanup", self._do_cleanup, list(rule_ids or []))
        return job.id

    def _do_cleanup(self, job, rule_ids):
        # remember which scanned folders are affected, to resync the tree afterwards
        tree = self._tree
        touched = []
        if tree is not None:
            rules = {r.id: r for r in cleanup.build_rules()}
            for rid in rule_ids:
                rule = rules.get(rid)
                if rule is None or rule.kind in ("info", "recycle"):
                    continue
                for root in self._rule_roots(rule):
                    if tree.covers(root) and tree.find_dir(root) is not None:
                        touched.append(root)
        res = cleanup.run_rules(job, rule_ids)
        errors = sum(r["errors"] for r in res["results"])
        self._log("cleanup", [r["name"] for r in res["results"]], res["freed"], "permanent", errors)
        if tree is not None:
            for p in touched[:40]:
                try:
                    if os.path.isdir(p):
                        self._graft(job, p)
                except Exception as exc:
                    print("graft failed", p, exc)
            self._insights_dirty = True
        return res

    def _rule_roots(self, rule):
        """Existing folders a rule touched (for re-syncing the scan tree)."""
        out = []
        for path in cleanup.resolve(rule):
            out.append(path if os.path.isdir(path) else os.path.dirname(path))
        if rule.kind == "old_ide":
            out = [os.path.dirname(p) for p in out]
        seen = set()
        uniq = []
        for p in out:
            k = norm(p)
            if k not in seen:
                seen.add(k)
                uniq.append(p)
        return uniq

    def cleanup_result(self):
        return self._cleanup

    # ------------------------------------------------------------------ actions
    def _size_of(self, path):
        tree = self._tree
        if tree is not None:
            node = tree.find_dir(path)
            if node is not None:
                return node.size
            _, f = tree.find_file(path)
            if f is not None:
                return f[1]
        return fsops.path_size(path)

    def start_delete(self, paths, mode="recycle", source="manual"):
        job = self._jobs.start("delete", self._do_delete, list(paths or []), mode, source)
        return job.id

    def _do_delete(self, job, paths, mode, source):
        failed = []
        ok = []
        freed = 0
        allowed = []
        for p in paths:
            level, reason = safety.classify(p, self._app_dir)
            if level == "blocked":
                failed.append({"path": p, "error": reason})
            elif not os.path.lexists(p):
                failed.append({"path": p, "error": "Not found (already deleted?)"})
            else:
                allowed.append(p)
        sizes = {p: self._size_of(p) for p in allowed}
        total = len(allowed)
        job.update(phase="delete", total=total, done=0, freed=0)
        if mode == "recycle":
            for i in range(0, total, 40):
                job.check()
                chunk = allowed[i:i + 40]
                res = winapi.send_to_recycle_bin(chunk)
                for p in chunk:
                    if res.get(p):
                        failed.append({"path": p, "error": res[p]})
                    else:
                        ok.append(p)
                        freed += sizes.get(p, 0)
                job.update(done=min(total, i + 40), freed=freed)
        else:
            for i, p in enumerate(allowed):
                job.check()
                f, _, errors = fsops.delete_tree(p, job=job)
                if os.path.lexists(p):
                    failed.append({"path": p, "error": errors[0][1] if errors else "Could not delete"})
                    freed += f
                else:
                    ok.append(p)
                    freed += sizes.get(p, f)
                job.update(done=i + 1, freed=freed)
        tree = self._tree
        if tree is not None:
            for p in ok:
                tree.remove_path(p, sizes.get(p))
            for item in failed:  # partially deleted folders: resync them
                if os.path.isdir(item["path"]) and tree.find_dir(item["path"]) is not None:
                    try:
                        self._graft(job, item["path"])
                    except Exception:
                        pass
            self._insights_dirty = True
            if self._dups:
                gone = {norm(p) for p in ok}
                for g in self._dups["groups"]:
                    g["files"] = [f for f in g["files"] if norm(f["path"]) not in gone]
                self._recount_dups()
        if ok:
            self._log("delete", [os.path.basename(p.rstrip("\\/")) or p for p in ok[:30]], freed, mode,
                      len(failed), {"count": len(ok), "source": source})
        return {"deleted": len(ok), "failed": failed, "freed": freed, "mode": mode, "ok_paths": ok}

    def start_move(self, paths, dest):
        if not dest:
            raise ValueError("Choose a destination folder")
        job = self._jobs.start("move", self._do_move, list(paths or []), dest)
        return job.id

    def _do_move(self, job, paths, dest):
        moved, failed, size = [], [], 0
        dest = os.path.abspath(dest)
        for i, p in enumerate(paths):
            job.check()
            job.update(phase="move", done=i, total=len(paths), current=p)
            level, reason = safety.classify(p, self._app_dir)
            if level == "blocked":
                failed.append({"path": p, "error": reason})
                continue
            if is_under(dest, p):
                failed.append({"path": p, "error": "Can't move a folder into itself"})
                continue
            s = self._size_of(p)
            try:
                target = fsops.move_path(p, dest)
                moved.append({"from": p, "to": target})
                size += s
                if self._tree is not None:
                    self._tree.remove_path(p, s)
            except OSError as exc:
                failed.append({"path": p, "error": exc.strerror or str(exc)})
        if self._tree is not None and self._tree.find_dir(dest) is not None and moved:
            try:
                self._graft(job, dest)
            except Exception:
                pass
        self._insights_dirty = True
        if moved:
            self._log("move", [os.path.basename(m["from"]) for m in moved[:30]], size, "move", len(failed),
                      {"dest": dest, "count": len(moved)})
        return {"moved": moved, "failed": failed, "size": size}

    def start_hardlink(self, groups):
        job = self._jobs.start("hardlink", self._do_hardlink, list(groups or []))
        return job.id

    def _do_hardlink(self, job, groups):
        saved, done, failed = 0, 0, []
        for i, g in enumerate(groups):
            job.check()
            job.update(phase="link", done=i, total=len(groups))
            keep = g.get("keep")
            for t in g.get("targets") or []:
                path = t.get("path") if isinstance(t, dict) else t
                level, reason = safety.classify(path, self._app_dir)
                if level == "blocked":
                    failed.append({"path": path, "error": reason})
                    continue
                try:
                    saved += fsops.replace_with_hardlink(keep, path, g.get("size"), t.get("mtime") if isinstance(t, dict) else None)
                    done += 1
                except OSError as exc:
                    failed.append({"path": path, "error": exc.strerror or str(exc)})
        if self._dups and done:
            keep_of = {}
            for g in groups:
                for t in g.get("targets") or []:
                    keep_of[norm(t.get("path") if isinstance(t, dict) else t)] = norm(g.get("keep") or "")
            for g in self._dups["groups"]:
                ino_by_path = {norm(f["path"]): f["ino"] for f in g["files"]}
                for f in g["files"]:
                    k = keep_of.get(norm(f["path"]))
                    if k and k in ino_by_path and os.path.exists(f["path"]):
                        f["linked"] = True
                        f["ino"] = ino_by_path[k]
            self._recount_dups()
        if done:
            self._log("hardlink", [f"{done} files"], saved, "hardlink", len(failed))
        return {"linked": done, "saved": saved, "failed": failed}

    # ------------------------------------------------------------------ apps
    def start_apps(self):
        job = self._jobs.start("apps", self._do_apps)
        return job.id

    def _generic_folder(self, path):
        """Folders that hold many apps - measuring them would credit one app with everything."""
        p = norm(path)
        home = os.path.expanduser("~")
        generic = {norm(x) for x in (
            os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("ProgramData", r"C:\ProgramData"), os.environ.get("SystemRoot", r"C:\Windows"), home,
            os.path.join(home, "AppData"), os.path.join(home, "AppData", "Local"), os.path.join(home, "AppData", "Roaming"),
            os.path.join(home, "AppData", "Local", "Programs"), os.path.dirname(home)) if x}
        return p in generic or len(os.path.splitdrive(p)[1].strip("\\/")) == 0

    def _do_apps(self, job):
        apps = winapi.installed_apps()
        tree = self._tree
        by_loc = {}
        for a in apps:
            if a["location"] and not self._generic_folder(a["location"]):
                by_loc.setdefault(norm(a["location"]), []).append(a)
        measured = {}
        for i, (key, group) in enumerate(by_loc.items()):
            job.check()
            loc = group[0]["location"]
            job.update(done=i, total=len(by_loc), current=group[0]["name"])
            node = tree.find_dir(loc) if tree is not None else None
            if node is not None:
                measured[key] = (node.size, "scan")
            else:
                try:
                    size, _ = fsops.dir_size(loc, job=job)
                    measured[key] = (size, "measured")
                except OSError:
                    pass
        total = 0
        counted = set()
        for a in apps:
            a["size"], a["source"], a["shared"] = a["estimated"], "registry", False
            key = norm(a["location"]) if a["location"] else None
            if key in measured and measured[key][0]:
                group = by_loc[key]
                if len(group) == 1:
                    a["size"], a["source"] = measured[key]
                elif not a["estimated"]:
                    # several apps share this folder: show the folder size once, flagged as shared
                    a["size"], a["source"], a["shared"] = measured[key][0], "shared", True
            if a["shared"]:
                if key not in counted:
                    counted.add(key)
                    total += a["size"]
            else:
                total += a["size"] or 0
        apps.sort(key=lambda x: -(x.get("size") or 0))
        self._apps = apps
        return {"apps": apps, "total": total}

    def uninstall(self, app_id):
        cmd = winapi.uninstall_command(app_id)
        if not cmd:
            raise ValueError("This app has no uninstaller registered")
        subprocess.Popen(cmd)
        return True

    # ------------------------------------------------------------------ history
    def snapshots(self, all_roots=False):
        if all_roots or self._tree is None:
            return snapshots.list_snapshots()
        return snapshots.history(self._tree.paths)

    def compare_snapshot(self, snap_id):
        return snapshots.compare_with_tree(self._require_tree(), snap_id)

    def delete_snapshot(self, snap_id):
        return snapshots.delete(snap_id)

    # ------------------------------------------------------------------ activity
    def activity(self):
        return self._activity

    def clear_activity(self):
        self._activity = {"entries": [], "freed": self._activity.get("freed", 0)}
        write_json(self._activity_path, self._activity)
        return True

    # ------------------------------------------------------------------ export
    def export(self, kind, opts=None):
        opts = opts or {}
        stamp = time.strftime("%Y%m%d-%H%M")
        if kind == "report":
            content, ext = self._html_report(), "html"
        else:
            content, ext = self._csv(kind, opts), "csv"
        name = f"SpaceHound-{kind}-{stamp}.{ext}"
        target = None
        if self._window is not None:
            import webview
            kind_save = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
            res = self._window.create_file_dialog(kind_save, save_filename=name)
            if not res:
                return None
            target = res[0] if isinstance(res, (list, tuple)) else res
        else:
            target = os.path.join(winapi.known_folder("Downloads"), name)
        with open(target, "w", encoding="utf-8-sig" if ext == "csv" else "utf-8", newline="") as fh:
            fh.write(content)
        return target

    def _csv(self, kind, opts):
        tree = self._tree
        buf = io.StringIO()
        w = csv.writer(buf)
        if kind == "largest":
            res = analysis.largest_files(self._require_tree(), dict(opts, limit=5000))
            w.writerow(["Path", "Size (bytes)", "Size", "Modified", "Category"])
            for r in res["items"]:
                w.writerow([r["path"], r["size"], fmt_size(r["size"]), time.strftime("%Y-%m-%d", time.localtime(r["mtime"])), r["cat"]])
        elif kind == "folders":
            self._require_tree()
            w.writerow(["Path", "Size (bytes)", "Size", "Files", "Folders", "Last change"])
            rows = []
            stack = [(tree.root, 0)]
            while stack:
                n, depth = stack.pop()
                if n.flags & F_REMOVED:
                    continue
                if depth:
                    rows.append(n)
                if depth < 6:
                    stack.extend((c, depth + 1) for c in n.dirs if c.size >= 10 << 20)
            rows.sort(key=lambda n: -n.size)
            for n in rows[:20000]:
                w.writerow([tree.path(n), n.size, fmt_size(n.size), n.nfiles, n.ndirs,
                            time.strftime("%Y-%m-%d", time.localtime(n.mtime)) if n.mtime else ""])
        elif kind == "types":
            res = analysis.type_stats(self._require_tree())
            w.writerow(["Extension", "Category", "Files", "Size (bytes)", "Size"])
            for e in res["exts"]:
                w.writerow([e["ext"], e["cat"], e["count"], e["size"], fmt_size(e["size"])])
        elif kind == "duplicates":
            if not self._dups:
                raise ValueError("Run the duplicate finder first")
            w.writerow(["Group", "Path", "Size (bytes)", "Size", "Wasted in group", "Hash"])
            for g in self._dups["groups"]:
                for f in g["files"]:
                    w.writerow([g["id"] + 1, f["path"], g["size"], fmt_size(g["size"]), fmt_size(g["wasted"]), g["hash"]])
        elif kind == "apps":
            w.writerow(["Name", "Publisher", "Version", "Size (bytes)", "Size", "Location"])
            for a in self._apps or []:
                w.writerow([a["name"], a["publisher"], a["version"], a.get("size") or 0, fmt_size(a.get("size") or 0), a["location"]])
        else:
            raise ValueError(f"Unknown export: {kind}")
        return buf.getvalue()

    def _html_report(self):
        s = self.scan_summary()
        if not s:
            raise ValueError("Run a scan first")
        esc = html.escape

        def rows(items, cols):
            return "".join("<tr>" + "".join(f"<td>{c(i)}</td>" for c in cols) + "</tr>" for i in items)

        cats = rows(s["categories"], [lambda c: f"<span class=dot style='background:{c['color']}'></span>{esc(c['label'])}",
                                      lambda c: fmt_size(c["size"]), lambda c: f"{c['count']:,}"])
        dirs = rows(s["deep"], [lambda d: esc(d["path"]), lambda d: fmt_size(d["size"]), lambda d: f"{d['files']:,}"])
        files = rows(analysis.largest_files(self._tree, {"limit": 50})["items"],
                     [lambda f: esc(f["path"]), lambda f: fmt_size(f["size"]),
                      lambda f: time.strftime("%Y-%m-%d", time.localtime(f["mtime"]))])
        ins = "".join(f"<li><b>{esc(i['title'])}</b><br><span>{esc(i['text'])}</span></li>" for i in s["insights"])
        return f"""<!doctype html><html><head><meta charset=utf-8><title>SpaceHound report</title>
<style>body{{font-family:Segoe UI,system-ui,sans-serif;background:#0f1218;color:#e7e9ee;max-width:1100px;margin:40px auto;padding:0 20px}}
h1{{font-weight:650}}h2{{margin-top:36px;font-weight:600;color:#c4b5fd}}table{{width:100%;border-collapse:collapse}}
td{{padding:7px 10px;border-bottom:1px solid #262b36;font-size:14px}}td:nth-child(2){{text-align:right;white-space:nowrap}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px}}li{{margin:10px 0}}li span{{color:#9aa3b5}}
.k{{display:inline-block;margin-right:28px}}.k b{{display:block;font-size:26px}}.muted{{color:#8a93a6}}</style></head><body>
<h1>SpaceHound report</h1><p class=muted>{esc(', '.join(s['roots']))} — {time.strftime('%Y-%m-%d %H:%M', time.localtime(s['finished'] or time.time()))}</p>
<div><span class=k><b>{fmt_size(s['size'])}</b>scanned</span><span class=k><b>{s['files']:,}</b>files</span><span class=k><b>{s['dirs']:,}</b>folders</span></div>
<h2>Insights</h2><ul>{ins}</ul><h2>By category</h2><table>{cats}</table><h2>Biggest folders</h2><table>{dirs}</table>
<h2>50 largest files</h2><table>{files}</table><p class=muted>Generated by SpaceHound {__version__}</p></body></html>"""

    # ------------------------------------------------------------------ lifecycle
    def _shutdown(self):
        self._jobs.cancel_all()
