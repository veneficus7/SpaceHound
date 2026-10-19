"""Thin ctypes wrappers around the Windows APIs SpaceHound needs.

Everything here degrades gracefully on non-Windows systems so the core
(scanner, duplicate finder) stays testable anywhere.
"""

import os
import shutil
import string
import subprocess
import sys
import uuid

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    import winreg

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    ole32 = ctypes.windll.ole32

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", ctypes.c_void_p),
            ("pTo", ctypes.c_void_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    class SHQUERYRBINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("i64Size", ctypes.c_longlong), ("i64NumItems", ctypes.c_longlong)]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        def __init__(self, text):
            super().__init__()
            u = uuid.UUID(text)
            self.Data1, self.Data2, self.Data3 = u.fields[0], u.fields[1], u.fields[2]
            for i, b in enumerate(u.bytes[8:]):
                self.Data4[i] = b

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
SHERB_NOCONFIRMATION, SHERB_NOPROGRESSUI, SHERB_NOSOUND = 1, 2, 4

DRIVE_TYPES = {0: "unknown", 1: "invalid", 2: "removable", 3: "fixed", 4: "network", 5: "cdrom", 6: "ramdisk"}

KNOWN_FOLDERS = {
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "Videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "Music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
}


def is_admin():
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def list_drives():
    drives = []
    if IS_WINDOWS:
        mask = kernel32.GetLogicalDrives()
        letters = [f"{c}:\\" for i, c in enumerate(string.ascii_uppercase) if mask & (1 << i)]
    else:
        letters = ["/"]
    for root in letters:
        info = {"path": root, "label": "", "fs": "", "type": "fixed", "total": 0, "used": 0, "free": 0, "ready": False}
        if IS_WINDOWS:
            info["type"] = DRIVE_TYPES.get(kernel32.GetDriveTypeW(root), "unknown")
            label = ctypes.create_unicode_buffer(261)
            fs = ctypes.create_unicode_buffer(261)
            old = kernel32.SetErrorMode(1)  # no "insert disk" popups
            try:
                if kernel32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261):
                    info["label"], info["fs"] = label.value, fs.value
            finally:
                kernel32.SetErrorMode(old)
        try:
            usage = shutil.disk_usage(root)
            info.update(total=usage.total, used=usage.used, free=usage.free, ready=True)
        except OSError:
            pass
        if info["type"] in ("cdrom",) and not info["ready"]:
            continue
        drives.append(info)
    return drives


def work_area():
    """(width, height) of the primary screen's work area in DPI-scaled (logical) pixels."""
    if not IS_WINDOWS:
        return None
    try:
        rect = wintypes.RECT()
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        dpi = user32.GetDpiForSystem() if hasattr(user32, "GetDpiForSystem") else 96
        scale = 96 / (dpi or 96)
        return int((rect.right - rect.left) * scale), int((rect.bottom - rect.top) * scale)
    except Exception:
        return None


def disk_usage(path):
    try:
        u = shutil.disk_usage(path)
        return {"total": u.total, "used": u.used, "free": u.free}
    except OSError:
        return None


def known_folder(name):
    if IS_WINDOWS and name in KNOWN_FOLDERS:
        ptr = ctypes.c_wchar_p()
        guid = GUID(KNOWN_FOLDERS[name])
        try:
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr)) == 0:
                value = ptr.value
                ole32.CoTaskMemFree(ptr)
                if value:
                    return value
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), name)


def known_folders():
    return {name: known_folder(name) for name in KNOWN_FOLDERS}


def recycle_bin_info(root=None):
    """(bytes, items) currently in the Recycle Bin (all drives when root is None)."""
    if not IS_WINDOWS:
        return 0, 0
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    if shell32.SHQueryRecycleBinW(root, ctypes.byref(info)) == 0:
        return int(info.i64Size), int(info.i64NumItems)
    return 0, 0


def empty_recycle_bin(root=None):
    if not IS_WINDOWS:
        return False
    hr = shell32.SHEmptyRecycleBinW(None, root, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
    # S_OK, or E_UNEXPECTED (0x8000FFFF) when it was already empty.
    return hr in (0, -2147418113)


def send_to_recycle_bin(paths):
    """Move paths to the Recycle Bin. Returns {path: error_or_None}."""
    results = {}
    if not IS_WINDOWS:
        for p in paths:
            results[p] = "Recycle Bin is only supported on Windows"
        return results
    for p in paths:
        results[p] = None
    clean = [os.path.abspath(p) for p in paths]
    buf = ctypes.create_unicode_buffer("\0".join(clean) + "\0")
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = ctypes.cast(buf, ctypes.c_void_p)
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    rc = shell32.SHFileOperationW(ctypes.byref(op))
    for original, p in zip(paths, clean):
        if os.path.lexists(p):
            results[original] = f"Could not move to Recycle Bin (code {rc:#x})" if rc else "File is in use or protected"
    return results


def reveal(path):
    """Open Explorer with the item selected."""
    if not IS_WINDOWS:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
        return
    path = os.path.abspath(path)
    pidl = shell32.ILCreateFromPathW(path)
    if pidl:
        try:
            ole32.CoInitialize(None)
            if shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == 0:
                return
        finally:
            shell32.ILFree(pidl)
    subprocess.Popen(f'explorer /select,"{path}"')


def open_path(path):
    if IS_WINDOWS:
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])


def shell_open(target):
    """Open a URL or ms-settings: link with the default handler."""
    if IS_WINDOWS:
        shell32.ShellExecuteW(None, "open", target, None, None, 1)


def set_clipboard(text):
    if not IS_WINDOWS:
        return False
    data = text.encode("utf-16-le") + b"\0\0"
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, len(data))
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(13, handle)
        return True
    finally:
        user32.CloseClipboard()


def relaunch_as_admin():
    """Restart the app elevated. Returns True when the elevated copy was started."""
    if not IS_WINDOWS:
        return False
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, subprocess.list2cmdline(sys.argv[1:])
    else:
        exe = sys.executable.replace("python.exe", "pythonw.exe") if sys.executable.endswith("python.exe") else sys.executable
        params = subprocess.list2cmdline(["-m", "spacehound"] + sys.argv[1:])
    cwd = os.getcwd()
    rc = shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1)
    return (rc or 0) > 32


# ---------------------------------------------------------------- installed apps

_UNINSTALL_KEYS = [
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0x0100),  # 64-bit view
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0x0200),  # 32-bit view
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0),
]


def _reg_value(key, name, default=None):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def installed_apps():
    if not IS_WINDOWS:
        return []
    apps, seen = [], set()
    for hive_name, path, view in _UNINSTALL_KEYS:
        hive = winreg.HKEY_LOCAL_MACHINE if hive_name == "HKLM" else winreg.HKEY_CURRENT_USER
        try:
            root = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    key = winreg.OpenKey(root, sub, 0, winreg.KEY_READ | view)
                except OSError:
                    continue
                with key:
                    name = _reg_value(key, "DisplayName")
                    if not name or _reg_value(key, "SystemComponent") == 1 or _reg_value(key, "ParentKeyName"):
                        continue
                    if str(_reg_value(key, "ReleaseType", "")).lower() in ("update", "hotfix", "security update"):
                        continue
                    version = str(_reg_value(key, "DisplayVersion", "") or "")
                    ident = (name.lower(), version)
                    if ident in seen:
                        continue
                    seen.add(ident)
                    est = _reg_value(key, "EstimatedSize", 0)
                    location = _reg_value(key, "InstallLocation", "") or ""
                    location = location.strip().strip('"')
                    apps.append({
                        "id": f"{hive_name}|{view}|{sub}",
                        "name": name,
                        "publisher": _reg_value(key, "Publisher", "") or "",
                        "version": version,
                        "installed": str(_reg_value(key, "InstallDate", "") or ""),
                        "estimated": int(est) * 1024 if isinstance(est, int) else 0,
                        "location": location if location and os.path.isdir(location) else "",
                        "can_uninstall": bool(_reg_value(key, "UninstallString")),
                    })
    return apps


def uninstall_command(app_id):
    """Look the uninstall command up again from the registry (never trust the UI)."""
    if not IS_WINDOWS:
        return None
    try:
        hive_name, view, sub = app_id.split("|", 2)
        view = int(view)
    except ValueError:
        return None
    for h, path, v in _UNINSTALL_KEYS:
        if h == hive_name and v == view:
            hive = winreg.HKEY_LOCAL_MACHINE if h == "HKLM" else winreg.HKEY_CURRENT_USER
            try:
                with winreg.OpenKey(hive, path + "\\" + sub, 0, winreg.KEY_READ | v) as key:
                    return _reg_value(key, "UninstallString")
            except OSError:
                return None
    return None


def steam_path():
    if not IS_WINDOWS:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            p = _reg_value(key, "SteamPath")
            return os.path.normpath(p) if p else None
    except OSError:
        return None
