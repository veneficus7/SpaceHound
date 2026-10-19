"""Per-user install / uninstall for the portable SpaceHound.exe (no admin rights needed).

install():   copies the exe to %LOCALAPPDATA%\\Programs\\SpaceHound, adds a Start menu
             shortcut (so Windows search finds it) and an "Apps & features" entry.
uninstall(): removes all of that again. Scan history and settings in
             %LOCALAPPDATA%\\SpaceHound are kept.
"""

import os
import shutil
import subprocess
import sys
import time

from . import APP_NAME, __version__
from .util import norm

IS_WINDOWS = os.name == "nt"
LOCAL = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
ROAMING = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
INSTALL_DIR = os.path.join(LOCAL, "Programs", APP_NAME)
INSTALLED_EXE = os.path.join(INSTALL_DIR, f"{APP_NAME}.exe")
START_MENU_LNK = os.path.join(ROAMING, "Microsoft", "Windows", "Start Menu", "Programs", f"{APP_NAME}.lnk")
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_NAME}"
REPO_URL = "https://github.com/veneficus7/SpaceHound"
CREATE_NO_WINDOW = 0x08000000


def _desktop_lnk():
    from .winapi import known_folder
    return os.path.join(known_folder("Desktop"), f"{APP_NAME}.lnk")


def current_exe():
    """The running SpaceHound.exe, or None when running from source."""
    return sys.executable if getattr(sys, "frozen", False) else None


def is_installed():
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY):
            return os.path.exists(INSTALLED_EXE)
    except OSError:
        return False


def status():
    exe = current_exe()
    return {
        "installed": is_installed(),
        "running_installed": bool(exe) and norm(exe) == norm(INSTALLED_EXE),
        "can_install": bool(exe) and IS_WINDOWS,
        "path": INSTALLED_EXE,
        "start_menu": os.path.exists(START_MENU_LNK),
        "desktop": IS_WINDOWS and os.path.exists(_desktop_lnk()),
    }


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def _make_shortcut(lnk, target):
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(lnk)}); "
        f"$s.TargetPath = {_ps_quote(target)}; "
        f"$s.WorkingDirectory = {_ps_quote(os.path.dirname(target))}; "
        f"$s.IconLocation = {_ps_quote(target + ',0')}; "
        "$s.Description = 'SpaceHound - find out what is eating your disk'; "
        "$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                   check=True, creationflags=CREATE_NO_WINDOW, capture_output=True)


def _register(exe):
    import winreg
    size_kb = os.path.getsize(exe) // 1024
    values = {
        "DisplayName": APP_NAME,
        "DisplayVersion": __version__,
        "Publisher": "SpaceHound contributors",
        "DisplayIcon": f'"{exe}",0',
        "InstallLocation": os.path.dirname(exe),
        "UninstallString": f'"{exe}" --uninstall',
        "QuietUninstallString": f'"{exe}" --uninstall --quiet',
        "URLInfoAbout": REPO_URL,
        "HelpLink": REPO_URL,
        "InstallDate": time.strftime("%Y%m%d"),
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)


def _notify_shell():
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED: refresh icons
    except Exception:
        pass


def install(desktop=False):
    """Install the running exe for the current user. Returns a status dict."""
    if not IS_WINDOWS:
        raise RuntimeError("Installing is only supported on Windows")
    src = current_exe()
    if not src:
        raise RuntimeError("Build SpaceHound.exe first (build.ps1) - installing works from the .exe")
    os.makedirs(INSTALL_DIR, exist_ok=True)
    if norm(src) != norm(INSTALLED_EXE):
        tmp = INSTALLED_EXE + ".new"
        shutil.copy2(src, tmp)
        try:
            os.replace(tmp, INSTALLED_EXE)
        except PermissionError:
            os.remove(tmp)
            raise RuntimeError("The installed SpaceHound is running - close it and try again")
    _make_shortcut(START_MENU_LNK, INSTALLED_EXE)
    if desktop:
        _make_shortcut(_desktop_lnk(), INSTALLED_EXE)
    _register(INSTALLED_EXE)
    _notify_shell()
    return status()


def uninstall():
    """Remove shortcuts, the Apps & features entry and the installed exe."""
    if not IS_WINDOWS:
        return status()
    import winreg
    for lnk in (START_MENU_LNK, _desktop_lnk()):
        try:
            os.remove(lnk)
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    exe = current_exe()
    if exe and norm(exe) == norm(INSTALLED_EXE):
        # we are the installed copy: delete the folder once this process has exited
        cmd = f'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "{INSTALL_DIR}"'
        subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW | 0x00000008, close_fds=True)  # DETACHED_PROCESS
    else:
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    _notify_shell()
    return status()


def message_box(text, title=APP_NAME, yes_no=False):
    """Native dialog for the --install / --uninstall command-line flows."""
    if not IS_WINDOWS:
        print(text)
        return True
    import ctypes
    flags = (0x04 | 0x20) if yes_no else 0x40  # MB_YESNO|MB_ICONQUESTION  or  MB_ICONINFORMATION
    return ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x00010000) in (1, 6)  # MB_SETFOREGROUND
