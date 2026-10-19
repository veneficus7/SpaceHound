"""Small helpers shared across the backend."""

import json
import os
import sys
import tempfile
import threading

_io_lock = threading.Lock()


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "SpaceHound")
    os.makedirs(path, exist_ok=True)
    return path


def resource_path(*parts):
    """Path to bundled resources, both from source and from a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def long_path(path):
    """Prefix a path with \\\\?\\ so Win32 calls accept paths longer than MAX_PATH."""
    if os.name != "nt" or path.startswith("\\\\?\\"):
        return path
    path = os.path.abspath(path)
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def maybe_long(path):
    return long_path(path) if len(path) >= 240 else path


def norm(path):
    return os.path.normcase(os.path.normpath(path))


def is_under(path, parent):
    """True when path equals parent or lives somewhere below it."""
    p, q = norm(path), norm(parent)
    if p == q:
        return True
    q = q if q.endswith(os.sep) else q + os.sep
    return p.startswith(q)


def fmt_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    """Atomic JSON write (temp file + rename) so a crash never leaves half a file."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    with _io_lock:
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


def expand(path):
    return os.path.expandvars(os.path.expanduser(path))
