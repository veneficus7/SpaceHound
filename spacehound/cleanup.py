"""Junk & cache cleanup rules.

Each rule names well-known, regenerable locations. Kinds:
* ``contents`` - delete everything inside the matched folders, keep the folder
* ``files``    - delete the matched files
* ``recycle``  - empty the Recycle Bin
* ``old_ide``  - older version folders of JetBrains IDEs / Android Studio
* ``info``     - measured and explained only; SpaceHound never deletes it
"""

import glob
import os
import re
import time

from . import winapi
from .fsops import delete_tree, dir_size

SAFE, MODERATE = "safe", "moderate"


class Rule:
    def __init__(self, rid, group, name, desc, paths=(), kind="contents", risk=SAFE, admin=False,
                 min_age_hours=0, open_target=None, tip=None):
        self.id = rid
        self.group = group
        self.name = name
        self.desc = desc
        self.paths = list(paths)
        self.kind = kind
        self.risk = risk
        self.admin = admin
        self.min_age_hours = min_age_hours
        self.open_target = open_target
        self.tip = tip


def _env(name, fallback=""):
    return os.environ.get(name) or fallback


def _expand(pattern):
    """Expand %VARS% and ~ while escaping glob characters inside the values."""
    def repl(m):
        value = os.environ.get(m.group(1))
        return glob.escape(value) if value else m.group(0)
    out = re.sub(r"%([^%]+)%", repl, pattern)
    if out.startswith("~"):
        out = glob.escape(os.path.expanduser("~")) + out[1:]
    return out


def _electron(app_dir):
    return [f"{app_dir}\\{sub}" for sub in ("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
                                            "DawnWebGPUCache", "Service Worker\\CacheStorage", "Service Worker\\ScriptCache")]


def _chromium(user_data):
    paths = []
    for sub in ("Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache",
                "Service Worker\\CacheStorage", "Service Worker\\ScriptCache", "Media Cache"):
        paths.append(f"{user_data}\\*\\{sub}")
    paths += [f"{user_data}\\ShaderCache", f"{user_data}\\GrShaderCache", f"{user_data}\\GraphiteDawnCache"]
    return paths


def build_rules():
    windir = _env("SystemRoot", r"C:\Windows")
    sysdrive = _env("SystemDrive", "C:")
    steam = winapi.steam_path()
    gradle_home = _env("GRADLE_USER_HOME") or "~\\.gradle"
    rules = [
        # ------------------------------------------------------------ Windows
        Rule("recycle", "Windows", "Recycle Bin", "Files you deleted earlier still use space until the bin is emptied.",
             kind="recycle", risk=MODERATE),
        Rule("user_temp", "Windows", "Temporary files (your account)",
             "Leftovers from installers and apps. Files changed in the last 24 h are kept because they may be in use.",
             ["%TEMP%"], min_age_hours=24),
        Rule("win_temp", "Windows", "Temporary files (Windows)", "System-wide temporary files older than 24 hours.",
             [windir + "\\Temp"], admin=True, min_age_hours=24),
        Rule("thumbs", "Windows", "Thumbnail & icon cache", "Explorer rebuilds thumbnails when needed.",
             ["%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\thumbcache_*.db",
              "%LOCALAPPDATA%\\Microsoft\\Windows\\Explorer\\iconcache_*.db"], kind="files"),
        Rule("inetcache", "Windows", "Internet cache (legacy)", "Cache used by old Internet Explorer components and some apps.",
             ["%LOCALAPPDATA%\\Microsoft\\Windows\\INetCache"]),
        Rule("wer", "Windows", "Error reports", "Crash reports Windows already sent (or never will).",
             ["%LOCALAPPDATA%\\Microsoft\\Windows\\WER", "%ProgramData%\\Microsoft\\Windows\\WER\\ReportArchive",
              "%ProgramData%\\Microsoft\\Windows\\WER\\ReportQueue", "%ProgramData%\\Microsoft\\Windows\\WER\\Temp"]),
        Rule("dumps", "Windows", "Crash dumps", "Memory dumps written when apps or Windows crashed. Only useful for debugging.",
             ["%LOCALAPPDATA%\\CrashDumps", windir + "\\Minidump", windir + "\\LiveKernelReports"]),
        Rule("memdump", "Windows", "Full memory dump", "MEMORY.DMP from a past blue screen - can be many GB.",
             [windir + "\\MEMORY.DMP"], kind="files", admin=True),
        Rule("wu_cache", "Windows", "Windows Update download cache", "Update packages that are already installed.",
             [windir + "\\SoftwareDistribution\\Download"], admin=True, risk=MODERATE),
        Rule("delivery", "Windows", "Delivery Optimization cache", "Update pieces shared with other PCs.",
             [windir + "\\ServiceProfiles\\NetworkService\\AppData\\Local\\Microsoft\\Windows\\DeliveryOptimization\\Cache"],
             admin=True),
        Rule("shader", "Windows", "DirectX / GPU shader caches", "Games and apps rebuild these automatically.",
             ["%LOCALAPPDATA%\\D3DSCache", "%LOCALAPPDATA%\\NVIDIA\\DXCache", "%LOCALAPPDATA%\\NVIDIA\\GLCache",
              "%LOCALAPPDATA%\\NVIDIA Corporation\\NV_Cache", "%ProgramData%\\NVIDIA Corporation\\NV_Cache",
              "%LOCALAPPDATA%\\AMD\\DxCache", "%LOCALAPPDATA%\\AMD\\DxcCache", "%LOCALAPPDATA%\\AMD\\GLCache",
              "%LOCALAPPDATA%\\AMD\\VkCache", "%LOCALAPPDATA%\\Intel\\ShaderCache"]),
        Rule("driver_leftovers", "Windows", "Driver installer leftovers", "Extracted NVIDIA/AMD driver packages kept after install.",
             [sysdrive + "\\AMD", "%ProgramData%\\NVIDIA Corporation\\Downloader"], risk=MODERATE),
        Rule("old_windows", "Windows", "Previous Windows installation",
             "Windows.old and upgrade leftovers. Remove them with Storage Sense or Disk Cleanup (they are owned by the system).",
             [sysdrive + "\\Windows.old", sysdrive + "\\$Windows.~BT", sysdrive + "\\$Windows.~WS", sysdrive + "\\ESD"],
             kind="info", open_target="ms-settings:storagepolicies"),
        Rule("hiberfil", "Windows", "Hibernation file",
             "hiberfil.sys is roughly 40% of your RAM. If you never hibernate, an admin terminal can shrink or remove it.",
             [sysdrive + "\\hiberfil.sys"], kind="info", tip="powercfg /h /type reduced|powercfg /h off"),
        Rule("pagefile", "Windows", "Page & swap files",
             "Virtual memory. Leave these to Windows unless you really know what you are doing.",
             [sysdrive + "\\pagefile.sys", sysdrive + "\\swapfile.sys"], kind="info"),
        Rule("winsxs", "Windows", "Component store (WinSxS)",
             "Superseded Windows components. Explorer over-reports its size because of hard links; DISM can trim it safely.",
             [windir + "\\WinSxS"], kind="info", tip="Dism.exe /Online /Cleanup-Image /StartComponentCleanup"),

        # ------------------------------------------------------------ Browsers
        Rule("chrome", "Browsers", "Google Chrome cache", "Cached web pages, images and scripts (not passwords, history or cookies).",
             _chromium("%LOCALAPPDATA%\\Google\\Chrome\\User Data")),
        Rule("edge", "Browsers", "Microsoft Edge cache", "Cached web content (not passwords, history or cookies).",
             _chromium("%LOCALAPPDATA%\\Microsoft\\Edge\\User Data")),
        Rule("brave", "Browsers", "Brave cache", "Cached web content.", _chromium("%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\User Data")),
        Rule("vivaldi", "Browsers", "Vivaldi cache", "Cached web content.", _chromium("%LOCALAPPDATA%\\Vivaldi\\User Data")),
        Rule("opera", "Browsers", "Opera cache", "Cached web content.",
             ["%LOCALAPPDATA%\\Opera Software\\Opera Stable\\Cache", "%LOCALAPPDATA%\\Opera Software\\Opera GX Stable\\Cache",
              "%APPDATA%\\Opera Software\\Opera Stable\\Code Cache", "%APPDATA%\\Opera Software\\Opera GX Stable\\Code Cache"]),
        Rule("firefox", "Browsers", "Firefox cache", "Cached web content (profiles and bookmarks are untouched).",
             ["%LOCALAPPDATA%\\Mozilla\\Firefox\\Profiles\\*\\cache2", "%LOCALAPPDATA%\\Mozilla\\Firefox\\Profiles\\*\\startupCache",
              "%LOCALAPPDATA%\\Mozilla\\Firefox\\Profiles\\*\\thumbnails"]),

        # ------------------------------------------------------------ Apps
        Rule("vscode", "Apps", "VS Code / Cursor caches", "Editor caches and downloaded extension packages.",
             _electron("%APPDATA%\\Code") + _electron("%APPDATA%\\Cursor") +
             ["%APPDATA%\\Code\\CachedData", "%APPDATA%\\Code\\CachedExtensionVSIXs", "%APPDATA%\\Code\\logs",
              "%APPDATA%\\Cursor\\CachedData", "%APPDATA%\\Cursor\\logs"]),
        Rule("discord", "Apps", "Discord cache", "Images and media Discord downloaded.", _electron("%APPDATA%\\discord")),
        Rule("slack", "Apps", "Slack cache", "Cached files and media.", _electron("%APPDATA%\\Slack")),
        Rule("teams", "Apps", "Microsoft Teams cache", "Cached files for classic and new Teams.",
             _electron("%APPDATA%\\Microsoft\\Teams") +
             ["%LOCALAPPDATA%\\Packages\\MSTeams_8wekyb3d8bbwe\\LocalCache\\Microsoft\\MSTeams\\EBWebView\\Default\\Cache",
              "%LOCALAPPDATA%\\Packages\\MSTeams_8wekyb3d8bbwe\\LocalCache\\Microsoft\\MSTeams\\EBWebView\\Default\\Code Cache"]),
        Rule("spotify", "Apps", "Spotify streaming cache", "Songs cached while streaming. Close Spotify first; offline downloads may need to re-download.",
             ["%LOCALAPPDATA%\\Spotify\\Storage", "%LOCALAPPDATA%\\Spotify\\Data",
              "%LOCALAPPDATA%\\Packages\\SpotifyAB.SpotifyMusic_*\\LocalCache\\Spotify\\Data",
              "%LOCALAPPDATA%\\Packages\\SpotifyAB.SpotifyMusic_*\\LocalCache\\Spotify\\Storage"]),
        Rule("adobe", "Apps", "Adobe disk & media caches",
             "After Effects disk cache, Premiere / After Effects media cache and audio peak files. Adobe rebuilds "
             "them when needed - your projects and footage are not touched. Close Adobe apps first.",
             ["%TEMP%\\Adobe\\After Effects\\*\\Disk Cache*", "%APPDATA%\\Adobe\\Common\\Media Cache Files",
              "%APPDATA%\\Adobe\\Common\\Media Cache", "%APPDATA%\\Adobe\\Common\\Peak Files",
              "%LOCALAPPDATA%\\Adobe\\*\\Cache"]),
        Rule("resolve", "Apps", "DaVinci Resolve caches", "Render cache and optimized-media leftovers in Resolve's support folder.",
             ["%APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\CacheClip",
              "%APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Resolve Disk Database\\*\\CacheClip"]),
        Rule("epic", "Apps", "Epic Games Launcher web cache", "Launcher web cache.",
             ["%LOCALAPPDATA%\\EpicGamesLauncher\\Saved\\webcache*"]),
        Rule("steam", "Apps", "Steam shader & web cache", "Shaders are recompiled on first launch of a game.",
             [glob.escape(steam) + "\\steamapps\\shadercache", glob.escape(steam) + "\\appcache\\httpcache",
              glob.escape(steam) + "\\dumps", glob.escape(steam) + "\\logs"] if steam else []),
        Rule("ide_caches", "Developer", "JetBrains / Android Studio caches & logs",
             "Caches and logs of IntelliJ, PyCharm, CLion, Android Studio… The IDE rebuilds them (first start is slower).",
             ["%LOCALAPPDATA%\\JetBrains\\*\\caches", "%LOCALAPPDATA%\\JetBrains\\*\\log", "%LOCALAPPDATA%\\JetBrains\\*\\tmp",
              "%LOCALAPPDATA%\\Google\\AndroidStudio*\\caches", "%LOCALAPPDATA%\\Google\\AndroidStudio*\\log",
              "%LOCALAPPDATA%\\Google\\AndroidStudio*\\tmp"], risk=MODERATE),
        Rule("old_ide", "Developer", "Old IDE versions",
             "Settings & caches of IDE versions you upgraded from (the newest version of each IDE is kept).",
             ["%LOCALAPPDATA%\\JetBrains\\*", "%APPDATA%\\JetBrains\\*",
              "%LOCALAPPDATA%\\Google\\AndroidStudio*", "%APPDATA%\\Google\\AndroidStudio*"], kind="old_ide", risk=MODERATE),

        # ------------------------------------------------------------ Developer
        Rule("gradle", "Developer", "Gradle caches", "Downloaded dependencies & build cache. Re-downloaded on the next build.",
             [gradle_home + "\\caches"], risk=MODERATE),
        Rule("gradle_dists", "Developer", "Gradle wrapper distributions", "Every Gradle version any project ever used (~150 MB each).",
             [gradle_home + "\\wrapper\\dists"], risk=MODERATE),
        Rule("gradle_daemon", "Developer", "Gradle daemon logs", "Log files of old Gradle daemons.", [gradle_home + "\\daemon"]),
        Rule("android_cache", "Developer", "Android SDK temp & cache", "Temporary SDK downloads and tool caches.",
             ["~\\.android\\cache", "%LOCALAPPDATA%\\Android\\Sdk\\.temp", "%LOCALAPPDATA%\\Android\\Sdk\\.downloadIntermediates"]),
        Rule("avd", "Developer", "Android emulators (AVDs)",
             "Each virtual device can take 5-15 GB. Delete unused ones from Android Studio > Device Manager.",
             ["~\\.android\\avd\\*.avd"], kind="info"),
        Rule("sysimages", "Developer", "Android system images",
             "Emulator images for each API level. Remove unused ones in Android Studio > SDK Manager.",
             ["%LOCALAPPDATA%\\Android\\Sdk\\system-images"], kind="info"),
        Rule("npm", "Developer", "npm / Yarn / pnpm caches", "Package download caches. Safe - packages are fetched again when needed.",
             ["%LOCALAPPDATA%\\npm-cache", "%APPDATA%\\npm-cache", "%LOCALAPPDATA%\\Yarn\\Cache", "%LOCALAPPDATA%\\Yarn\\Berry\\cache",
              "%LOCALAPPDATA%\\pnpm-cache", "~\\.bun\\install\\cache"]),
        Rule("pip", "Developer", "Python package caches", "pip, uv and Poetry download caches.",
             ["%LOCALAPPDATA%\\pip\\cache", "%LOCALAPPDATA%\\uv\\cache", "%LOCALAPPDATA%\\pypoetry\\Cache"]),
        Rule("conda", "Developer", "Conda package cache", "Extracted packages kept after installing (same as `conda clean --all`).",
             ["~\\anaconda3\\pkgs", "~\\miniconda3\\pkgs", "%ProgramData%\\anaconda3\\pkgs", "%ProgramData%\\miniconda3\\pkgs"],
             risk=MODERATE),
        Rule("nuget", "Developer", "NuGet caches", "HTTP & plugin caches of NuGet.",
             ["%LOCALAPPDATA%\\NuGet\\v3-cache", "%LOCALAPPDATA%\\NuGet\\plugins-cache", "%TEMP%\\NuGetScratch"]),
        Rule("nuget_pkgs", "Developer", "NuGet global packages", ".NET projects restore them again on build.",
             ["~\\.nuget\\packages"], risk=MODERATE),
        Rule("maven", "Developer", "Maven repository", "Downloaded Maven artifacts; re-downloaded on demand.",
             ["~\\.m2\\repository"], risk=MODERATE),
        Rule("cargo", "Developer", "Cargo registry cache", "Downloaded crate archives and sources.",
             ["~\\.cargo\\registry\\cache", "~\\.cargo\\registry\\src", "~\\.cargo\\git\\checkouts"]),
        Rule("go", "Developer", "Go build & module cache", "Same as `go clean -cache -modcache`.",
             ["%LOCALAPPDATA%\\go-build", "~\\go\\pkg\\mod"], risk=MODERATE),
        Rule("pub", "Developer", "Dart / Flutter pub cache", "Downloaded packages; `flutter pub get` restores them.",
             ["%LOCALAPPDATA%\\Pub\\Cache"], risk=MODERATE),
        Rule("docker", "Developer", "Docker / WSL virtual disks",
             "Virtual disks grow but never shrink by themselves. Run `docker system prune`, then compact the disk.",
             ["%LOCALAPPDATA%\\Docker\\wsl\\disk\\*.vhdx", "%LOCALAPPDATA%\\Docker\\wsl\\data\\*.vhdx",
              "%LOCALAPPDATA%\\Docker\\wsl\\main\\*.vhdx", "%LOCALAPPDATA%\\Packages\\*\\LocalState\\ext4.vhdx",
              "%LOCALAPPDATA%\\wsl\\*\\ext4.vhdx"], kind="info", tip="docker system prune -a|wsl --shutdown|Optimize-VHD -Path <path-to.vhdx> -Mode Full"),
    ]
    return [r for r in rules if r.paths or r.kind == "recycle"]


_VERSION_RE = re.compile(r"^(?P<product>[A-Za-z][A-Za-z\-]*?)(?P<version>\d{4}(?:\.\d+)*)$")


def _old_ide_dirs(rule):
    """Folders like PyCharm2023.2 when PyCharm2024.1 also exists."""
    found = {}
    for pattern in rule.paths:
        for path in glob.glob(_expand(pattern)):
            if not os.path.isdir(path):
                continue
            m = _VERSION_RE.match(os.path.basename(path))
            if not m:
                continue
            parent = os.path.dirname(path).lower()
            version = tuple(int(x) for x in m.group("version").split("."))
            found.setdefault((parent, m.group("product").lower()), []).append((version, path))
    old = []
    for versions in found.values():
        versions.sort()
        old.extend(p for _, p in versions[:-1])
    return old


def resolve(rule):
    if rule.kind == "old_ide":
        return _old_ide_dirs(rule)
    out = []
    seen = set()
    for pattern in rule.paths:
        for path in glob.glob(_expand(pattern)):
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                out.append(path)
    return out


def _claims(rules, resolved):
    """Every (rule id, folder) pair - used so overlapping rules never count a file twice."""
    out = []
    for r in rules:
        if r.kind == "recycle":
            continue
        for p in resolved.get(r.id, ()):
            out.append((r.id, os.path.normcase(os.path.abspath(p))))
    return out


def _skip_for(rule_id, path, claims):
    base = os.path.normcase(os.path.abspath(path))
    prefix = base.rstrip("\\/") + os.sep
    return {q for rid, q in claims if rid != rule_id and q.startswith(prefix)}


def _measure_rule(rule, job, paths, claims):
    if rule.kind == "recycle":
        size, items = winapi.recycle_bin_info()
        return size, items, []
    older = time.time() - rule.min_age_hours * 3600 if rule.min_age_hours else None
    total = count = 0
    found = []
    for path in paths:
        if job.cancelled:
            break
        if os.path.isdir(path):
            size, n = dir_size(path, job=job, older_than=older, skip=_skip_for(rule.id, path, claims))
        else:
            try:
                size, n = os.stat(path).st_size, 1
            except OSError:
                continue
        if size or n:
            total += size
            count += n
            found.append({"path": path, "size": size})
    found.sort(key=lambda x: -x["size"])
    return total, count, found


def scan_rules(job, is_admin):
    rules = build_rules()
    resolved = {r.id: resolve(r) for r in rules if r.kind != "recycle"}
    claims = _claims(rules, resolved)
    items = []
    for i, rule in enumerate(rules):
        job.check()
        job.update(phase="measure", done=i, total=len(rules), current=rule.name)
        size, count, found = _measure_rule(rule, job, resolved.get(rule.id, ()), claims)
        if rule.kind != "recycle" and not found:
            continue
        items.append({
            "id": rule.id, "group": rule.group, "name": rule.name, "desc": rule.desc, "kind": rule.kind,
            "risk": rule.risk, "admin": rule.admin, "needs_admin": rule.admin and not is_admin,
            "size": size, "count": count, "paths": found[:50], "open": rule.open_target, "tip": rule.tip,
        })
    job.update(done=len(rules), total=len(rules))
    items.sort(key=lambda x: (["Windows", "Browsers", "Apps", "Developer"].index(x["group"]), x["kind"] == "info", -x["size"]))
    return {"items": items, "total": sum(x["size"] for x in items if x["kind"] != "info")}


def run_rules(job, rule_ids):
    """Clean the selected rules. Returns per-rule freed bytes and errors."""
    all_rules = build_rules()
    rules = {r.id: r for r in all_rules}
    resolved = {r.id: resolve(r) for r in all_rules if r.kind != "recycle"}
    claims = _claims(all_rules, resolved)
    results = []
    freed_total = 0
    selected = [rules[r] for r in rule_ids if r in rules and rules[r].kind != "info"]
    for i, rule in enumerate(selected):
        job.check()
        job.update(phase="clean", done=i, total=len(selected), current=rule.name, freed=freed_total)
        freed, deleted, errors = 0, 0, []
        if rule.kind == "recycle":
            before, _ = winapi.recycle_bin_info()
            ok = winapi.empty_recycle_bin()
            after, _ = winapi.recycle_bin_info()
            freed = max(0, before - after)
            if not ok and before:
                errors.append(("Recycle Bin", "Could not empty the Recycle Bin"))
        else:
            older = time.time() - rule.min_age_hours * 3600 if rule.min_age_hours else None
            for path in resolved.get(rule.id, ()):
                if job.cancelled:
                    break
                keep_root = rule.kind == "contents"
                skip = _skip_for(rule.id, path, claims) if os.path.isdir(path) else None
                f, d, e = delete_tree(path, job=job, older_than=older, keep_root=keep_root, skip=skip)
                freed += f
                deleted += d
                errors.extend(e)
        freed_total += freed
        results.append({"id": rule.id, "name": rule.name, "freed": freed, "deleted": deleted,
                        "errors": len(errors), "error_samples": [f"{p}: {m}" for p, m in errors[:5]]})
    return {"results": results, "freed": freed_total}
