"""Guard rails: decide whether a path may be deleted from the UI.

``classify`` returns one of
* ``("blocked", reason)`` - SpaceHound refuses to touch it,
* ``("warn", reason)``    - allowed, but the UI shows an extra warning,
* ``("ok", "")``.
Cleanup rules (temp folders, caches) use their own allow-list and do not go
through this check.
"""

import os

from .util import is_under, norm

_ENV = os.environ.get


def _system_roots():
    windir = _ENV("SystemRoot") or _ENV("WINDIR") or r"C:\Windows"
    drive = os.path.splitdrive(windir)[0] or "C:"
    home = os.path.expanduser("~")
    users = os.path.dirname(home)
    blocked_tree = [
        windir,
        _ENV("ProgramFiles") or drive + r"\Program Files",
        _ENV("ProgramFiles(x86)") or drive + r"\Program Files (x86)",
        _ENV("ProgramW6432") or drive + r"\Program Files",
        drive + r"\Program Files\WindowsApps",
        drive + r"\Recovery",
        drive + r"\Boot",
        drive + r"\EFI",
        drive + r"\$WinREAgent",
    ]
    blocked_exact = [
        _ENV("ProgramData") or drive + r"\ProgramData",
        users,
        home,
        os.path.join(home, "AppData"),
        os.path.join(home, "AppData", "Local"),
        os.path.join(home, "AppData", "Roaming"),
        os.path.join(home, "AppData", "LocalLow"),
        os.path.join(home, "OneDrive"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Pictures"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Music"),
        os.path.join(users, "Public"),
        os.path.join(users, "Default"),
    ]
    warn_tree = [
        _ENV("ProgramData") or drive + r"\ProgramData",
        os.path.join(home, "AppData"),
    ]
    return blocked_tree, blocked_exact, warn_tree


_BLOCKED_TREE, _BLOCKED_EXACT, _WARN_TREE = _system_roots()
_BLOCKED_NAMES = {"$recycle.bin", "system volume information", "pagefile.sys", "hiberfil.sys",
                  "swapfile.sys", "bootmgr", "bootnxt", "dumpstack.log.tmp", "$mft", "config.msi"}

_extra_protected = []


def set_user_protected(paths):
    global _extra_protected
    _extra_protected = [p for p in (paths or []) if p]


def classify(path, app_dir=None):
    if not path:
        return "blocked", "Empty path"
    p = os.path.abspath(path)
    drive, rest = os.path.splitdrive(p)
    if rest in ("", "\\", "/"):
        return "blocked", "Drive roots can't be deleted"
    if os.path.basename(p).lower() in _BLOCKED_NAMES:
        return "blocked", "Windows system file"
    # "<drive>:\$Recycle.Bin\..." and "System Volume Information\..." anywhere on any drive
    parts = [x.lower() for x in rest.strip("\\/").split(os.sep)]
    if parts and parts[0] in _BLOCKED_NAMES:
        return "blocked", "Windows system area"
    for root in _BLOCKED_TREE:
        if root and is_under(p, root):
            return "blocked", f"Inside a protected system folder ({root})"
    np = norm(p)
    for exact in _BLOCKED_EXACT:
        if exact and np == norm(exact):
            return "blocked", "Essential user/system folder (you can delete things inside it)"
    for user in _extra_protected:
        if is_under(p, user):
            return "blocked", f"Protected in Settings ({user})"
    if app_dir and is_under(p, app_dir):
        return "blocked", "SpaceHound's own files"
    for root in _WARN_TREE:
        if root and is_under(p, root):
            return "warn", "App data folder - programs may lose settings or stop working"
    return "ok", ""


def summarize(paths, app_dir=None):
    out = []
    for p in paths:
        level, reason = classify(p, app_dir)
        out.append({"path": p, "level": level, "reason": reason})
    return out
