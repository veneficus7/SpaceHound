"""Create a realistic demo folder for screenshots and manual testing.

Big files are NTFS *sparse* files: they report their full size to scanners
but take (almost) no real disk space. A few small real files are duplicated so
the duplicate finder has something to find.

    python scripts/make_demo.py D:\\SpaceHound-Demo
"""

import ctypes
import msvcrt
import os
import random
import shutil
import sys
import time

GB, MB = 1 << 30, 1 << 20
DAY = 86400
random.seed(42)
NOW = time.time()


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                      ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
_kernel32.DeviceIoControl.restype = ctypes.c_int
_kernel32.SetFilePointerEx.argtypes = [ctypes.c_void_p, ctypes.c_longlong, ctypes.c_void_p, ctypes.c_ulong]
_kernel32.SetFilePointerEx.restype = ctypes.c_int
_kernel32.SetEndOfFile.argtypes = [ctypes.c_void_p]
_kernel32.SetEndOfFile.restype = ctypes.c_int
_kernel32.GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
_kernel32.GetCompressedFileSizeW.restype = ctypes.c_ulong

_free_at_start = None


def allocated_size(path):
    """Bytes really used on disk (small for a sparse file)."""
    high = ctypes.c_ulong()
    low = _kernel32.GetCompressedFileSizeW(path, ctypes.byref(high))
    return (high.value << 32) + low


def sparse(path, size, age_days=0):
    """Create a file that *reports* ``size`` bytes but allocates (almost) nothing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        handle = msvcrt.get_osfhandle(fh.fileno())
        ret = ctypes.c_ulong()
        if not _kernel32.DeviceIoControl(handle, 0x900C4, None, 0, None, 0, ctypes.byref(ret), None):  # FSCTL_SET_SPARSE
            raise OSError(ctypes.get_last_error(), f"Could not mark {path} as sparse (needs NTFS)")
        # Never use fh.truncate(): the C runtime extends files by *writing zeros*, which allocates real space.
        if not _kernel32.SetFilePointerEx(handle, int(size), None, 0) or not _kernel32.SetEndOfFile(handle):
            raise OSError(ctypes.get_last_error(), f"Could not size {path}")
    used = allocated_size(path)
    if used > 1 << 20:
        os.remove(path)
        raise RuntimeError(f"{path} allocated {used} bytes - aborting so no real disk space is used")
    free = shutil.disk_usage(os.path.splitdrive(os.path.abspath(path))[0] + "\\").free
    if _free_at_start - free > 1 << 30:
        raise RuntimeError("Free space dropped by more than 1 GB - aborting")
    touch(path, age_days)


def real(path, data, age_days=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    touch(path, age_days)


def touch(path, age_days):
    if age_days:
        t = NOW - age_days * DAY - random.randint(0, DAY)
        os.utime(path, (t, t))


def jitter(base, spread=0.35):
    return int(base * (1 + random.uniform(-spread, spread)))


def main(root):
    global _free_at_start
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    _free_at_start = shutil.disk_usage(root).free
    j = lambda *p: os.path.join(root, *p)

    # Videos
    for i, name in enumerate(["A001_C002_raw.mov", "A001_C007_raw.mov", "B002_C011_raw.mov", "drone_4k_01.mov"]):
        sparse(j("Videos", "Wedding 2023", "Footage", name), jitter(30 * GB), 420 + i)
    sparse(j("Videos", "Wedding 2023", "Final cut v3.mp4"), 9.4 * GB, 400)
    sparse(j("Videos", "Wedding 2023", "Final cut v2.mp4"), 9.1 * GB, 405)
    for i in range(24):
        sparse(j("Videos", "Screen recordings", f"Recording {2024}-{(i % 12) + 1:02d}-{i + 3:02d}.mp4"), jitter(900 * MB, 0.8), random.randint(10, 500))
    for name in ["Interstellar.mkv", "Dune Part Two.mkv", "Oppenheimer.mkv", "The Matrix.mkv", "Arrival.mkv", "Blade Runner 2049.mkv"]:
        sparse(j("Videos", "Movies", name), jitter(4.2 * GB), random.randint(200, 1200))

    # Pictures (+ real duplicates)
    for year in range(2019, 2025):
        for i in range(70):
            sparse(j("Pictures", "Camera Roll", str(year), f"IMG_{year}{i:04d}.jpg"), jitter(4.5 * MB), (2025 - year) * 365)
    for i in range(30):
        data = os.urandom(random.randint(900, 2400) * 1024)
        real(j("Pictures", "Favourites", f"IMG_FAV_{i:03d}.jpg"), data, 300)
        real(j("Pictures", "Phone backup (copy)", f"IMG_FAV_{i:03d}.jpg"), data, 120)
        if i % 3 == 0:
            real(j("Desktop", "to sort", f"IMG_FAV_{i:03d} (1).jpg"), data, 30)

    # Downloads
    for name, size, age in [("Win11_24H2_English_x64.iso", 5.8 * GB, 380), ("ubuntu-24.04-desktop-amd64.iso", 5.7 * GB, 300),
                            ("DaVinci_Resolve_Studio_19_Windows.zip", 3.2 * GB, 220), ("SteamSetup.exe", 2.3 * MB, 600),
                            ("Blender-4.2-windows-x64.msi", 340 * MB, 150), ("AndroidStudio-2024.exe", 1.2 * GB, 260),
                            ("Course recordings.zip", 7.9 * GB, 500), ("node-v22-x64.msi", 31 * MB, 90)]:
        sparse(j("Downloads", name), size, age)

    # Games
    for game, n in [("Cyber Racer", 8), ("Space Colony", 5)]:
        for i in range(n):
            sparse(j("Games", "SteamLibrary", "steamapps", "common", game, "Content", f"pak{i:02d}.pak"), jitter(6 * GB), 60)
    for i in range(140):
        sparse(j("Games", "SteamLibrary", "steamapps", "shadercache", f"{i:04d}", "fozpipelinesv6", "steamapprun_pipeline_cache.foz"), jitter(9 * MB), 20)

    # Developer projects
    real(j("Projects", "web-shop", "package.json"), b'{"name": "web-shop"}', 240)
    real(j("Projects", "web-shop", "src", "index.ts"), b"export {}", 240)
    for i in range(260):
        sparse(j("Projects", "web-shop", "node_modules", f"pkg-{i:03d}", "dist", "index.js"), jitter(3 * MB, 0.9), 240)
    real(j("Projects", "fitness-android", "build.gradle.kts"), b"// gradle", 35)
    real(j("Projects", "fitness-android", "settings.gradle.kts"), b'include(":app")', 35)
    real(j("Projects", "fitness-android", "app", "build.gradle.kts"), b"// gradle", 35)
    for i in range(40):
        sparse(j("Projects", "fitness-android", "app", "build", "intermediates", f"dex{i}", "classes.dex"), jitter(25 * MB), 35)
    for i in range(20):
        sparse(j("Projects", "fitness-android", ".gradle", "8.9", f"cache{i}.bin"), jitter(14 * MB), 35)
    real(j("Projects", "rust-cli", "Cargo.toml"), b'[package]\nname="cli"', 420)
    for i in range(30):
        sparse(j("Projects", "rust-cli", "target", "debug", "deps", f"lib{i}.rlib"), jitter(60 * MB), 420)
    real(j("Projects", "ml-experiments", ".venv", "pyvenv.cfg"), b"home = C:\\Python312", 150)
    for i in range(50):
        sparse(j("Projects", "ml-experiments", ".venv", "Lib", "site-packages", f"torch{i}", "lib.pyd"), jitter(70 * MB), 150)
    sparse(j("Projects", "ml-experiments", "models", "llama-8b-q4.gguf"), 4.9 * GB, 140)
    sparse(j("Projects", "ml-experiments", "models", "sdxl-base.safetensors"), 6.9 * GB, 145)

    # Virtual machines
    sparse(j("Virtual Machines", "Ubuntu Dev", "Ubuntu Dev.vhdx"), 64 * GB, 90)
    sparse(j("Virtual Machines", "Windows Test", "Windows Test.vhdx"), 38 * GB, 700)

    # Music
    for a in range(12):
        for t in range(14):
            sparse(j("Music", "FLAC", f"Artist {a + 1:02d}", f"Album {a % 3 + 1}", f"{t + 1:02d} Track.flac"), jitter(32 * MB), 900)

    # Old backups nobody looked at for years
    for i in range(10):
        sparse(j("Backups", "Old laptop 2019", "Documents", f"archive_{i}.zip"), jitter(1.6 * GB), 1900)
    sparse(j("Backups", "Old laptop 2019", "phone_backup_2018.tar"), 22 * GB, 2300)

    # Documents
    for i in range(80):
        sparse(j("Documents", "University", f"Lecture {i + 1:02d}.pdf"), jitter(6 * MB, 0.9), random.randint(200, 1400))
    for i in range(40):
        sparse(j("Documents", "Work", f"Report Q{i % 4 + 1} {2021 + i // 10}.docx"), jitter(2 * MB, 0.9), random.randint(30, 900))

    # Caches & temp
    for i in range(300):
        sparse(j("AppCache", "VideoEditor", "Render cache", f"{i:05d}.aecache"), jitter(28 * MB), 14)
    for name in ["Empty project", "New folder", "New folder (2)"]:
        os.makedirs(j("Desktop", name), exist_ok=True)
    print("demo created at", root)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else r"D:\SpaceHound-Demo")
