"""Core engine tests. Run with:  python -m unittest discover -s tests -v"""

import os
import shutil
import stat
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spacehound import analysis, cleanup, devjunk, duplicates, fsops, safety, snapshots  # noqa: E402
from spacehound.jobs import Job  # noqa: E402
from spacehound.scanner import F_LINK, scan  # noqa: E402

KB, MB = 1024, 1024 * 1024


def write(path, data=b"", size=None, age_days=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if size is None else os.urandom(size))
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
    return path


class TempTree(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="spacehound-test-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def p(self, *parts):
        return os.path.join(self.root, *parts)


class ScannerTests(TempTree):
    def test_sizes_counts_and_threshold(self):
        write(self.p("a", "big.bin"), size=200 * KB)
        write(self.p("a", "small.txt"), size=10 * KB)
        write(self.p("a", "b", "c.mp4"), size=300 * KB)
        write(self.p("top.txt"), b"hello")
        tree = scan(Job(1, "t"), [self.root], threads=4, threshold=64 * KB)
        self.assertEqual(tree.root.size, 200 * KB + 10 * KB + 300 * KB + 5)
        self.assertEqual(tree.root.nfiles, 4)
        self.assertEqual(tree.root.ndirs, 2)
        a = tree.find_dir(self.p("a"))
        self.assertEqual([f[0] for f in a.files], ["big.bin"])     # stored individually
        self.assertEqual((a.small_n, a.small_size), (1, 10 * KB))  # summarized
        self.assertEqual(tree.path(tree.find_dir(self.p("a", "b"))), self.p("a", "b"))

    def test_remove_path_updates_totals(self):
        write(self.p("x", "one.bin"), size=100 * KB)
        write(self.p("x", "two.bin"), size=100 * KB)
        tree = scan(Job(1, "t"), [self.root], threads=2, threshold=64 * KB)
        removed = tree.remove_path(self.p("x", "one.bin"))
        self.assertEqual(removed, 100 * KB)
        self.assertEqual(tree.root.size, 100 * KB)
        tree.remove_path(self.p("x"))
        self.assertEqual(tree.root.size, 0)
        self.assertIsNone(tree.find_dir(self.p("x")))

    @unittest.skipUnless(os.name == "nt", "junctions are Windows-only")
    def test_junctions_are_not_followed(self):
        import _winapi
        write(self.p("real", "data.bin"), size=100 * KB)
        _winapi.CreateJunction(self.p("real"), self.p("link"))
        tree = scan(Job(1, "t"), [self.root], threads=2, threshold=64 * KB)
        self.assertEqual(tree.root.size, 100 * KB)  # counted once, not twice
        self.assertTrue(tree.find_dir(self.p("link")).flags & F_LINK)

    def test_largest_and_filters(self):
        write(self.p("v", "movie.mkv"), size=500 * KB, age_days=800)
        write(self.p("v", "clip.mp4"), size=300 * KB)
        write(self.p("d", "doc.pdf"), size=200 * KB)
        tree = scan(Job(1, "t"), [self.root], threads=2, threshold=64 * KB)
        res = analysis.largest_files(tree, {"limit": 10})
        self.assertEqual([r["name"] for r in res["items"]], ["movie.mkv", "clip.mp4", "doc.pdf"])
        res = analysis.largest_files(tree, {"cats": ["video"], "older_days": 365})
        self.assertEqual([r["name"] for r in res["items"]], ["movie.mkv"])
        res = analysis.largest_files(tree, {"query": "*.pdf"})
        self.assertEqual(res["matched"], 1)


class DuplicateTests(TempTree):
    def test_finds_identical_and_ignores_same_size(self):
        blob = os.urandom(300 * KB)
        write(self.p("a", "photo.jpg"), blob)
        write(self.p("b", "photo copy.jpg"), blob)
        write(self.p("c", "other.jpg"), size=300 * KB)      # same size, different bytes
        write(self.p("d", "head-same.bin"), blob[:-1] + b"X")  # differs only at the end
        res = duplicates.find_duplicates(Job(1, "d"), None, [self.root], min_size=1)
        self.assertEqual(len(res["groups"]), 1)
        names = sorted(os.path.basename(f["path"]) for f in res["groups"][0]["files"])
        self.assertEqual(names, ["photo copy.jpg", "photo.jpg"])
        self.assertEqual(res["wasted"], 300 * KB)

    def test_hardlinks_are_not_reported_as_waste(self):
        blob = os.urandom(200 * KB)
        a = write(self.p("a.bin"), blob)
        os.link(a, self.p("b.bin"))
        res = duplicates.find_duplicates(Job(1, "d"), None, [self.root], min_size=1)
        self.assertEqual(res["groups"], [])

    def test_replace_with_hardlink(self):
        blob = os.urandom(150 * KB)
        a = write(self.p("a.bin"), blob)
        b = write(self.p("b.bin"), blob)
        saved = fsops.replace_with_hardlink(a, b)
        self.assertEqual(saved, 150 * KB)
        self.assertEqual(os.stat(a).st_ino, os.stat(b).st_ino)
        with open(b, "rb") as fh:
            self.assertEqual(fh.read(), blob)


class SafetyTests(unittest.TestCase):
    def test_system_paths_blocked(self):
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        self.assertEqual(safety.classify(windir)[0], "blocked")
        self.assertEqual(safety.classify(os.path.join(windir, "System32", "drivers"))[0], "blocked")
        self.assertEqual(safety.classify("C:\\")[0], "blocked")
        self.assertEqual(safety.classify(os.path.expanduser("~"))[0], "blocked")
        self.assertEqual(safety.classify(r"C:\pagefile.sys")[0], "blocked")

    def test_normal_paths_allowed(self):
        p = os.path.join(os.path.expanduser("~"), "Downloads", "old-installer.exe")
        self.assertEqual(safety.classify(p)[0], "ok")
        self.assertEqual(safety.classify(os.path.join(os.path.expanduser("~"), "AppData", "Local", "x"))[0], "warn")

    def test_user_protected(self):
        safety.set_user_protected([r"D:\Precious"])
        try:
            self.assertEqual(safety.classify(r"D:\Precious\photo.jpg")[0], "blocked")
        finally:
            safety.set_user_protected([])


class FsOpsTests(TempTree):
    def test_delete_tree_handles_readonly_and_keep_root(self):
        f = write(self.p("cache", "sub", "ro.dat"), size=KB)
        os.chmod(f, stat.S_IREAD)
        write(self.p("cache", "x.tmp"), size=2 * KB)
        freed, deleted, errors = fsops.delete_tree(self.p("cache"), keep_root=True)
        self.assertEqual((freed, deleted, errors), (3 * KB, 2, []))
        self.assertTrue(os.path.isdir(self.p("cache")))
        self.assertEqual(os.listdir(self.p("cache")), [])

    def test_delete_tree_age_filter(self):
        write(self.p("t", "old.tmp"), size=KB, age_days=5)
        write(self.p("t", "new.tmp"), size=KB)
        fsops.delete_tree(self.p("t"), keep_root=True, older_than=time.time() - 86400)
        self.assertEqual(os.listdir(self.p("t")), ["new.tmp"])

    def test_skip_set_is_respected(self):
        write(self.p("temp", "a.tmp"), size=KB)
        write(self.p("temp", "Adobe", "cache.bin"), size=KB)
        skip = {os.path.normcase(self.p("temp", "Adobe"))}
        self.assertEqual(fsops.dir_size(self.p("temp"), skip=skip), (KB, 1))
        fsops.delete_tree(self.p("temp"), keep_root=True, skip=skip)
        self.assertTrue(os.path.exists(self.p("temp", "Adobe", "cache.bin")))


class CleanupTests(unittest.TestCase):
    def test_overlapping_rules_are_skipped(self):
        claims = [("user_temp", os.path.normcase(r"C:\T")), ("adobe", os.path.normcase(r"C:\T\Adobe\AE\Disk Cache"))]
        self.assertEqual(cleanup._skip_for("user_temp", r"C:\T", claims), {os.path.normcase(r"C:\T\Adobe\AE\Disk Cache")})
        self.assertEqual(cleanup._skip_for("adobe", r"C:\T\Adobe\AE\Disk Cache", claims), set())

    def test_rules_build(self):
        ids = [r.id for r in cleanup.build_rules()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("user_temp", ids)


class SnapshotTests(unittest.TestCase):
    def test_compare_reports_most_specific_folder(self):
        old = {r"C:\U": 100 * MB, r"C:\U\Videos": 60 * MB, r"C:\U\Videos\New": 0}
        new = {r"C:\U": 400 * MB, r"C:\U\Videos": 360 * MB, r"C:\U\Videos\New": 300 * MB}
        changes = snapshots.compare(old, new, [r"C:\U"], min_delta=50 * MB)
        self.assertEqual(changes[0]["path"], r"C:\U\Videos\New")
        self.assertEqual(len(changes), 1)


class DevJunkTests(TempTree):
    def test_node_modules_needs_package_json(self):
        write(self.p("proj", "package.json"), b"{}")
        write(self.p("proj", "node_modules", "lib", "index.js"), size=2 * MB)
        write(self.p("notaproj", "node_modules", "x.js"), size=2 * MB)
        tree = scan(Job(1, "t"), [self.root], threads=2, threshold=64 * KB)
        res = devjunk.find_artifacts(tree, min_size=MB)
        self.assertEqual([p["name"] for p in res["projects"]], ["proj"])

    def test_gradle_module_grouped_under_root(self):
        write(self.p("app1", "settings.gradle.kts"), b"")
        write(self.p("app1", "app", "build.gradle.kts"), b"")
        write(self.p("app1", "app", "build", "out.apk"), size=2 * MB)
        tree = scan(Job(1, "t"), [self.root], threads=2, threshold=64 * KB)
        res = devjunk.find_artifacts(tree, min_size=MB)
        self.assertEqual([p["name"] for p in res["projects"]], ["app1"])


if __name__ == "__main__":
    unittest.main()
