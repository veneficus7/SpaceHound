"""Fast, parallel directory scanner that builds a compact in-memory tree.

Design notes
------------
* ``os.scandir`` on Windows returns size, timestamps and attributes straight
  from FindNextFileW, so no extra syscall per file is needed.
* Every directory becomes a ``DirNode``. Files at or above ``threshold`` bytes
  are stored individually (name, size, mtime) - they hold ~99% of the bytes on
  a typical disk. Smaller files are only counted per directory, which keeps
  memory use low even for millions of files.
* Junctions and directory symlinks (name-surrogate reparse points) are never
  followed, so nothing is counted twice. OneDrive / cloud placeholders are
  traversed, but cloud-only files are reported separately because they do not
  occupy local disk space.
"""

import os
import queue
import threading
import time
from bisect import bisect_right

from .categories import EXT_TO_CAT, OTHER, ext_of
from .util import is_under, maybe_long, norm

ATTR_HIDDEN = 0x2
ATTR_SYSTEM = 0x4
ATTR_DIRECTORY = 0x10
ATTR_REPARSE = 0x400
CLOUD_MASK = 0x1000 | 0x40000 | 0x400000  # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS
NAME_SURROGATE = 0x20000000

F_DENIED = 1        # this folder could not be read
F_LINK = 2          # junction / symlink, not followed
F_HIDDEN = 4
F_SYSTEM = 8
F_VIRTUAL = 16      # synthetic "This PC" root
F_ROOT = 32         # a scanned root; its name is an absolute path
F_SUB_DENIED = 64   # something below could not be read
F_SUB_LINK = 128    # a link lives somewhere below
F_EXCLUDED = 256    # skipped by user settings
F_REMOVED = 512     # deleted after the scan

AGE_EDGES_DAYS = [30, 182, 365, 730, 1825]
AGE_LABELS = ["< 1 month", "1–6 months", "6–12 months", "1–2 years", "2–5 years", "5+ years"]
SIZE_EDGES = [1 << 10, 1 << 20, 10 << 20, 100 << 20, 1 << 30]
SIZE_LABELS = ["< 1 KB", "1 KB – 1 MB", "1 – 10 MB", "10 – 100 MB", "100 MB – 1 GB", "> 1 GB"]

SEP = os.sep
_EMPTY = ()


class DirNode:
    __slots__ = ("idx", "name", "parent", "dirs", "files", "own_size", "small_n", "small_size",
                 "size", "nfiles", "ndirs", "mtime", "own_mtime", "cloud", "flags")

    def __init__(self, name, parent, flags=0):
        self.idx = 0
        self.name = name
        self.parent = parent
        self.dirs = _EMPTY
        self.files = _EMPTY      # list of (name, size, mtime), largest first after finalize
        self.own_size = 0        # bytes of files directly inside
        self.small_n = 0         # files below the threshold (not stored individually)
        self.small_size = 0
        self.size = 0            # subtree bytes (local files only)
        self.nfiles = 0          # subtree file count
        self.ndirs = 0           # subtree folder count
        self.mtime = 0           # newest modification time in the subtree
        self.own_mtime = 0       # newest modification time of direct files
        self.cloud = 0           # subtree bytes that live only in the cloud
        self.flags = flags


def normalize_root(path):
    path = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
    if len(path) == 2 and path[1] == ":":
        path += SEP
    path = os.path.abspath(path)
    return path


class ScanTree:
    def __init__(self, paths, threshold):
        self.lock = threading.RLock()
        self.threshold = threshold
        self.paths = [normalize_root(p) for p in paths]
        self.nodes = []
        if len(self.paths) == 1:
            self.root = DirNode(self.paths[0], None, F_ROOT)
            self.roots = [self.root]
        else:
            self.root = DirNode("This PC", None, F_VIRTUAL)
            self.roots = [DirNode(p, self.root, F_ROOT) for p in self.paths]
            self.root.dirs = list(self.roots)
        self.nodes.append(self.root)
        if self.root not in self.roots:
            self.nodes.extend(self.roots)
        self.ext_stats = {}                     # ext -> [count, bytes]
        self.age_hist = [[0, 0] for _ in AGE_LABELS]
        self.size_hist = [[0, 0] for _ in SIZE_LABELS]
        self.denied = []
        self.denied_count = 0
        self.files_seen = 0
        self.dirs_seen = 0
        self.bytes_seen = 0
        self.current = ""
        self.started = time.time()
        self.finished = None
        self.drive_usage = {}

    # ---------------------------------------------------------------- paths
    def path(self, node):
        names = []
        n = node
        while n is not None and not (n.flags & F_ROOT):
            if n.flags & F_VIRTUAL:
                return ""
            names.append(n.name)
            n = n.parent
        if n is None:
            return ""
        base = n.name
        if not names:
            return base
        rel = SEP.join(reversed(names))
        return base + rel if base.endswith(SEP) else base + SEP + rel

    def file_path(self, node, name):
        base = self.path(node)
        return base + name if base.endswith(SEP) else base + SEP + name

    def get(self, idx):
        try:
            node = self.nodes[int(idx)]
        except (IndexError, ValueError, TypeError):
            return None
        return None if node.flags & F_REMOVED else node

    def depth(self, node):
        d = 0
        while node.parent is not None:
            d += 1
            node = node.parent
        return d

    def _root_for(self, path):
        best = None
        for r in self.roots:
            if is_under(path, r.name) and (best is None or len(r.name) > len(best.name)):
                best = r
        return best

    def find_dir(self, path):
        path = os.path.abspath(path)
        root = self._root_for(path)
        if root is None:
            return None
        rel = path[len(root.name):].strip("\\/")
        node = root
        if not rel:
            return node
        for comp in rel.replace("/", SEP).split(SEP):
            low = comp.lower()
            for child in node.dirs:
                if child.name.lower() == low:
                    node = child
                    break
            else:
                return None
        return None if node.flags & F_REMOVED else node

    def find_file(self, path):
        parent = self.find_dir(os.path.dirname(os.path.abspath(path)))
        if parent is None:
            return None, None
        low = os.path.basename(path).lower()
        for f in parent.files:
            if f[0].lower() == low:
                return parent, f
        return parent, None

    def covers(self, path):
        return self._root_for(os.path.abspath(path)) is not None

    # ---------------------------------------------------------------- iteration
    def iter_dirs(self, node=None):
        stack = [node or self.root]
        while stack:
            n = stack.pop()
            if n.flags & F_REMOVED:
                continue
            yield n
            if n.dirs:
                stack.extend(n.dirs)

    def iter_files(self, node=None):
        for d in self.iter_dirs(node):
            for f in d.files:
                yield d, f

    # ---------------------------------------------------------------- mutation
    def _propagate(self, node, dsize, dfiles, ddirs, dcloud=0):
        while node is not None:
            node.size += dsize
            node.nfiles += dfiles
            node.ndirs += ddirs
            node.cloud += dcloud
            node = node.parent

    def _ext_sub(self, name, size):
        st = self.ext_stats.get(ext_of(name))
        if st:
            st[0] = max(0, st[0] - 1)
            st[1] = max(0, st[1] - size)

    def remove_path(self, path, size_hint=None):
        """Reflect a deletion in the tree. Returns bytes removed from the tree."""
        with self.lock:
            node = self.find_dir(path)
            if node is not None and node.parent is not None:
                parent = node.parent
                try:
                    parent.dirs.remove(node)
                except ValueError:
                    return 0
                for _, f in self.iter_files(node):
                    self._ext_sub(f[0], f[1])
                node.flags |= F_REMOVED
                self._propagate(parent, -node.size, -node.nfiles, -(node.ndirs + 1), -node.cloud)
                return node.size
            parent, f = self.find_file(path)
            if parent is None:
                return 0
            if f is not None:
                parent.files.remove(f)
                parent.own_size -= f[1]
                self._ext_sub(f[0], f[1])
                self._propagate(parent, -f[1], -1, 0)
                return f[1]
            if size_hint is not None and parent.small_n > 0:
                size = min(size_hint, parent.small_size)
                parent.small_n -= 1
                parent.small_size -= size
                parent.own_size -= size
                self._propagate(parent, -size, -1, 0)
                return size
            return 0


def scan(job, paths, threads=12, threshold=64 * 1024, excluded=()):
    """Scan ``paths`` and return a finalized ScanTree. ``job`` receives progress."""
    tree = ScanTree(paths, threshold)
    for p in tree.paths:
        if not os.path.isdir(p):
            raise FileNotFoundError(f"Folder not found: {p}")
    excluded_norm = {norm(p) for p in excluded if p}
    now = time.time()
    age_times = sorted(now - d * 86400 for d in AGE_EDGES_DAYS)
    ext_cat = EXT_TO_CAT
    nodes_append = tree.nodes.append
    lock = threading.Lock()
    work = queue.LifoQueue()
    pending = [0]
    done = threading.Event()

    def process(node, path):
        try:
            it = os.scandir(maybe_long(path))
        except OSError:
            node.flags |= F_DENIED
            with lock:
                tree.denied_count += 1
                if len(tree.denied) < 1000:
                    tree.denied.append(path)
            return _EMPTY
        own_size = small_n = small_size = own_mtime = cloud = 0
        files = dirs = None
        subs = []
        ext_local = {}
        age_c = [0] * 6
        age_b = [0] * 6
        size_c = [0] * 6
        size_b = [0] * 6
        prefix = path if path.endswith(SEP) else path + SEP
        try:
            with it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    a = st.st_file_attributes
                    if a & ATTR_DIRECTORY:
                        fl = 0
                        if a & ATTR_HIDDEN:
                            fl |= F_HIDDEN
                        if a & ATTR_SYSTEM:
                            fl |= F_SYSTEM
                        child = DirNode(e.name, node, fl)
                        nodes_append(child)
                        if dirs is None:
                            dirs = []
                        dirs.append(child)
                        if a & ATTR_REPARSE and st.st_reparse_tag & NAME_SURROGATE:
                            child.flags |= F_LINK
                            continue
                        cpath = prefix + e.name
                        if excluded_norm and norm(cpath) in excluded_norm:
                            child.flags |= F_EXCLUDED
                            continue
                        subs.append((child, cpath))
                        continue
                    if a & ATTR_REPARSE and st.st_reparse_tag & NAME_SURROGATE:
                        continue  # file symlink - the target is counted where it lives
                    s = st.st_size
                    if a & CLOUD_MASK:
                        cloud += s
                        continue
                    m = int(st.st_mtime)
                    own_size += s
                    if m > own_mtime:
                        own_mtime = m
                    name = e.name
                    ext = ext_of(name)
                    es = ext_local.get(ext)
                    if es is None:
                        ext_local[ext] = [1, s]
                    else:
                        es[0] += 1
                        es[1] += s
                    ab = 5 - bisect_right(age_times, m)
                    age_c[ab] += 1
                    age_b[ab] += s
                    sb = bisect_right(SIZE_EDGES, s)
                    size_c[sb] += 1
                    size_b[sb] += s
                    if s >= threshold:
                        if files is None:
                            files = []
                        files.append((name, s, m))
                    else:
                        small_n += 1
                        small_size += s
        except OSError:
            node.flags |= F_DENIED
        if files:
            node.files = files
        if dirs:
            node.dirs = dirs
            node.ndirs = len(dirs)
        n_files = small_n + (len(files) if files else 0)
        node.own_size = own_size
        node.size = own_size
        node.small_n = small_n
        node.small_size = small_size
        node.nfiles = n_files
        node.mtime = own_mtime
        node.own_mtime = own_mtime
        node.cloud = cloud
        with lock:
            stats = tree.ext_stats
            for ext, (c, s) in ext_local.items():
                g = stats.get(ext)
                if g is None:
                    stats[ext] = [c, s]
                else:
                    g[0] += c
                    g[1] += s
            for i in range(6):
                if age_c[i]:
                    tree.age_hist[i][0] += age_c[i]
                    tree.age_hist[i][1] += age_b[i]
                if size_c[i]:
                    tree.size_hist[i][0] += size_c[i]
                    tree.size_hist[i][1] += size_b[i]
            tree.files_seen += n_files
            tree.dirs_seen += 1
            tree.bytes_seen += own_size
            tree.current = path
        return subs

    def worker():
        while not job.cancelled:
            try:
                item = work.get(timeout=0.05)
            except queue.Empty:
                if done.is_set():
                    return
                continue
            node, path = item
            try:
                subs = process(node, path)
            except Exception:  # never let one odd folder kill the scan
                node.flags |= F_DENIED
                subs = _EMPTY
            with lock:
                pending[0] += len(subs) - 1
                finished = pending[0] == 0
            for s in subs:
                work.put(s)
            if finished:
                done.set()

    for r in tree.roots:
        pending[0] += 1
        work.put((r, r.name))

    workers = [threading.Thread(target=worker, name=f"scan-{i}", daemon=True) for i in range(max(1, threads))]
    for w in workers:
        w.start()
    while not done.is_set() and not job.cancelled:
        job.update(files=tree.files_seen, dirs=tree.dirs_seen, bytes=tree.bytes_seen,
                   current=tree.current, denied=tree.denied_count)
        done.wait(0.15)
    for w in workers:
        w.join()
    job.check()

    job.update(phase="finalizing", files=tree.files_seen, dirs=tree.dirs_seen, bytes=tree.bytes_seen)
    finalize(tree)
    for r in tree.roots:
        drive = os.path.splitdrive(r.name)[0] + SEP if os.name == "nt" else "/"
        if norm(r.name) == norm(drive):
            try:
                import shutil
                u = shutil.disk_usage(drive)
                tree.drive_usage[r.name] = {"total": u.total, "used": u.used, "free": u.free}
            except OSError:
                pass
    tree.finished = time.time()
    return tree


def finalize(tree):
    """Assign stable ids, roll subtree totals up to the parents and sort children."""
    nodes = tree.nodes
    for i, n in enumerate(nodes):
        n.idx = i
    size_key = _size_key
    for n in reversed(nodes):  # children always come after their parent
        if n.files:
            n.files.sort(key=size_key, reverse=True)
        if n.dirs:
            n.dirs.sort(key=_dir_size_key, reverse=True)
        p = n.parent
        if p is None:
            continue
        p.size += n.size
        p.nfiles += n.nfiles
        p.ndirs += n.ndirs
        p.cloud += n.cloud
        if n.mtime > p.mtime:
            p.mtime = n.mtime
        if n.flags & (F_DENIED | F_SUB_DENIED):
            p.flags |= F_SUB_DENIED
        if n.flags & (F_LINK | F_SUB_LINK):
            p.flags |= F_SUB_LINK


def _size_key(f):
    return f[1]


def _dir_size_key(d):
    return d.size


def category_of_file(name):
    return ext_cat_get(ext_of(name))


def ext_cat_get(ext):
    return EXT_TO_CAT.get(ext, OTHER)
