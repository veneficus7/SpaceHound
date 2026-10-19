"""Find regenerable build artifacts inside software projects.

Works on the scan tree (no extra disk walk). A folder only counts as an
artifact when the project marker next to it exists, e.g. ``node_modules`` needs
a ``package.json`` beside it, ``build`` needs a Gradle/Flutter/CMake project.
"""

import glob
import os
import time

from .scanner import F_LINK, F_REMOVED, F_ROOT

# name -> (kind, check) where check(parent_path, artifact_path) -> bool


def _has(*names):
    def check(parent, _path):
        return any(os.path.exists(os.path.join(parent, n)) for n in names)
    return check


def _has_glob(*patterns):
    def check(parent, _path):
        esc = glob.escape(parent)
        return any(glob.glob(os.path.join(esc, p)) for p in patterns)
    return check


def _inside(*names):
    def check(_parent, path):
        return any(os.path.exists(os.path.join(path, n)) for n in names)
    return check


def _always(_parent, _path):
    return True


def _either(*checks):
    def check(parent, path):
        return any(c(parent, path) for c in checks)
    return check


GRADLE = ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")

ARTIFACTS = {
    "node_modules": ("Node.js", _has("package.json")),
    ".next": ("Next.js", _has("package.json")),
    ".nuxt": ("Nuxt", _has("package.json")),
    ".svelte-kit": ("SvelteKit", _has("package.json")),
    ".parcel-cache": ("Parcel", _has("package.json")),
    ".turbo": ("Turborepo", _has("package.json")),
    ".angular": ("Angular cache", _has("angular.json")),
    "build": ("Build output", _either(_has(*GRADLE), _has("pubspec.yaml"), _inside("CMakeCache.txt"))),
    ".gradle": ("Gradle (project)", _has(*GRADLE, "gradlew")),
    ".cxx": ("Android NDK", _has(*GRADLE)),
    ".externalNativeBuild": ("Android NDK", _has(*GRADLE)),
    "target": ("Rust / Maven", _has("Cargo.toml", "pom.xml")),
    ".dart_tool": ("Dart / Flutter", _has("pubspec.yaml")),
    "Pods": ("CocoaPods", _has("Podfile")),
    "bin": (".NET", _has_glob("*.csproj", "*.fsproj", "*.vbproj")),
    "obj": (".NET", _has_glob("*.csproj", "*.fsproj", "*.vbproj")),
    "__pycache__": ("Python bytecode", _always),
    ".venv": ("Python virtualenv", _inside("pyvenv.cfg")),
    "venv": ("Python virtualenv", _inside("pyvenv.cfg")),
    "env": ("Python virtualenv", _inside("pyvenv.cfg")),
    ".tox": ("Python tox", _always),
    ".pytest_cache": ("pytest cache", _always),
    ".mypy_cache": ("mypy cache", _always),
    ".ruff_cache": ("Ruff cache", _always),
    "Library": ("Unity", lambda parent, _p: os.path.isdir(os.path.join(parent, "Assets")) and
                os.path.isdir(os.path.join(parent, "ProjectSettings"))),
    "Intermediate": ("Unreal Engine", _has_glob("*.uproject")),
    "DerivedDataCache": ("Unreal Engine", _has_glob("*.uproject")),
    ".terraform": ("Terraform", _has_glob("*.tf")),
}
PREFIX_ARTIFACTS = {"cmake-build-": ("CMake / CLion", _has("CMakeLists.txt"))}

# never look inside these (app data, package caches handled by Cleanup, VCS internals)
SKIP_NAMES = {"appdata", "$recycle.bin", "system volume information", "windowsapps", ".git", ".hg", ".svn",
              ".m2", ".nuget", ".cargo", ".rustup", ".npm", ".android", ".vscode", ".cache", "site-packages",
              "anaconda3", "miniconda3", ".pyenv"}
SKIP_AT_ROOT = {"windows", "program files", "program files (x86)", "programdata"}
_LOWER_ARTIFACTS = {k.lower(): k for k in ARTIFACTS}


def _match(name):
    low = name.lower()
    key = _LOWER_ARTIFACTS.get(low)
    if key is not None:
        return ARTIFACTS[key]
    for prefix, spec in PREFIX_ARTIFACTS.items():
        if low.startswith(prefix):
            return spec
    return None


def _is_artifact_name(name):
    low = name.lower()
    return low in _LOWER_ARTIFACTS or any(low.startswith(p) for p in PREFIX_ARTIFACTS)


def _project_activity(node, limit=30000):
    """Newest mtime in a project, ignoring its build artifacts."""
    newest = node.own_mtime
    stack = [d for d in node.dirs if not _is_artifact_name(d.name)]
    seen = 0
    while stack and seen < limit:
        n = stack.pop()
        seen += 1
        if n.own_mtime > newest:
            newest = n.own_mtime
        stack.extend(d for d in n.dirs if not _is_artifact_name(d.name))
    return newest


def find_artifacts(tree, start=None, min_size=1 << 20):
    start = start or tree.root
    found = []
    stack = [start]
    checked = 0
    while stack:
        node = stack.pop()
        for child in node.dirs:
            if child.flags & (F_LINK | F_REMOVED):
                continue
            low = child.name.lower()
            if low in SKIP_NAMES or (node.flags & F_ROOT and low in SKIP_AT_ROOT):
                continue
            spec = _match(child.name)
            if spec is not None and child.size >= min_size:
                path = tree.path(child)
                parent_path = os.path.dirname(path)
                checked += 1
                try:
                    ok = spec[1](parent_path, path)
                except OSError:
                    ok = False
                if ok:
                    found.append((child, spec[0], path))
                    continue  # never look inside an artifact
            if child.dirs:
                stack.append(child)

    root_markers = ("settings.gradle", "settings.gradle.kts", ".git", "pnpm-workspace.yaml", "lerna.json",
                    "nx.json", "turbo.json", "go.work", "WORKSPACE")
    root_cache = {}

    def project_root(node):
        """Climb from a module (e.g. Android ``app``) to the real project root, max 3 levels."""
        best = node
        cur = node
        for _ in range(3):
            if cur.parent is None or cur.flags & F_ROOT:
                break
            cur = cur.parent
            if cur.idx not in root_cache:
                p = tree.path(cur)
                root_cache[cur.idx] = bool(p) and (any(os.path.exists(os.path.join(p, m)) for m in root_markers)
                                                   or bool(glob.glob(os.path.join(glob.escape(p), "*.sln"))))
            if root_cache[cur.idx]:
                best = cur
        return best

    projects = {}
    for node, kind, path in found:
        proj = project_root(node.parent)
        key = proj.idx
        entry = projects.get(key)
        if entry is None:
            proj_path = tree.path(proj)
            entry = projects[key] = {
                "id": proj.idx, "path": proj_path, "name": os.path.basename(proj_path.rstrip("\\/")) or proj_path,
                "size": 0, "kinds": [], "artifacts": [], "last_active": _project_activity(proj),
            }
        entry["artifacts"].append({"id": node.idx, "path": path, "name": node.name, "kind": kind,
                                   "size": node.size, "files": node.nfiles})
        entry["size"] += node.size
        if kind not in entry["kinds"]:
            entry["kinds"].append(kind)
    out = sorted(projects.values(), key=lambda p: -p["size"])
    now = time.time()
    for p in out:
        p["artifacts"].sort(key=lambda a: -a["size"])
        p["idle_days"] = int((now - p["last_active"]) / 86400) if p["last_active"] else None
    return {"projects": out, "total": sum(p["size"] for p in out), "checked": checked}
