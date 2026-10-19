"""File system operations: walking, sizing, deleting, moving, hard-linking.

None of these follow junctions or symlinks: a link is removed as a link and
its target is left alone.
"""

import os
import shutil
import stat
import time

from .util import maybe_long

ATTR_DIRECTORY = 0x10
ATTR_REPARSE = 0x400
CLOUD_MASK = 0x1000 | 0x40000 | 0x400000


def _is_link_dir(entry, st):
    attrs = getattr(st, "st_file_attributes", 0)
    return entry.is_symlink() or bool(attrs & ATTR_REPARSE and getattr(st, "st_reparse_tag", 0) & 0x20000000)


def walk_files(root, job=None, min_mtime=None, max_mtime=None, skip=None):
    """Yield (path, size, mtime) for local files below root.

    ``skip`` is a set of normcased folder paths that are not entered."""
    stack = [root]
    while stack:
        if job is not None and job.cancelled:
            return
        path = stack.pop()
        if skip and path != root and os.path.normcase(path) in skip:
            continue
        try:
            it = os.scandir(maybe_long(path))
        except OSError:
            continue
        prefix = path if path.endswith(os.sep) else path + os.sep
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                attrs = getattr(st, "st_file_attributes", 0)
                if e.is_dir(follow_symlinks=False) or attrs & ATTR_DIRECTORY:
                    if not _is_link_dir(e, st):
                        stack.append(prefix + e.name)
                    continue
                if e.is_symlink() or attrs & CLOUD_MASK:
                    continue
                m = st.st_mtime
                if min_mtime is not None and m < min_mtime:
                    continue
                if max_mtime is not None and m > max_mtime:
                    continue
                yield prefix + e.name, st.st_size, int(m)


def dir_size(root, job=None, older_than=None, skip=None):
    """(bytes, files) below root. ``older_than`` = only count files modified before this time."""
    total = count = 0
    for _, size, _ in walk_files(root, job=job, max_mtime=older_than, skip=skip):
        total += size
        count += 1
    return total, count


def path_size(path):
    try:
        st = os.stat(maybe_long(path), follow_symlinks=False)
    except OSError:
        return 0
    if stat.S_ISDIR(st.st_mode) and not os.path.islink(path):
        return dir_size(path)[0]
    return st.st_size


def _force_remove(path):
    try:
        os.remove(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)  # read-only files (git objects, Go module cache)
        os.remove(path)


def _remove_link_or_dir(path):
    try:
        os.rmdir(path)
    except OSError:
        os.unlink(path)


def delete_tree(root, job=None, older_than=None, keep_root=False, on_progress=None, skip=None):
    """Permanently delete root (or only its contents when keep_root).

    Never follows links. Files that are locked are skipped and reported.
    ``older_than`` restricts deletion to files last modified before that time.
    ``skip`` is a set of normcased folder paths left untouched.
    Returns (freed_bytes, deleted_files, errors[list of (path, message)]).
    """
    freed = deleted = 0
    errors = []
    lroot = maybe_long(root)
    try:
        st = os.stat(lroot, follow_symlinks=False)
    except OSError as exc:
        return 0, 0, [(root, str(exc))]
    attrs = getattr(st, "st_file_attributes", 0)
    if not stat.S_ISDIR(st.st_mode) or attrs & ATTR_REPARSE:
        if keep_root:
            return 0, 0, []
        try:
            if stat.S_ISDIR(st.st_mode):
                _remove_link_or_dir(lroot)
                return 0, 0, []
            _force_remove(lroot)
            return st.st_size, 1, []
        except OSError as exc:
            return 0, 0, [(root, exc.strerror or str(exc))]

    # iterative post-order walk
    stack = [(root, False)]
    while stack:
        if job is not None and job.cancelled:
            break
        path, visited = stack.pop()
        lpath = maybe_long(path)
        if visited:
            if keep_root and path == root:
                continue
            try:
                os.rmdir(lpath)
            except OSError as exc:
                if older_than is None:  # with an age filter, non-empty folders are expected
                    errors.append((path, exc.strerror or str(exc)))
            continue
        stack.append((path, True))
        try:
            it = os.scandir(lpath)
        except OSError as exc:
            errors.append((path, exc.strerror or str(exc)))
            continue
        prefix = path if path.endswith(os.sep) else path + os.sep
        with it:
            for e in it:
                child = prefix + e.name
                try:
                    est = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                eattrs = getattr(est, "st_file_attributes", 0)
                is_dir = e.is_dir(follow_symlinks=False) or bool(eattrs & ATTR_DIRECTORY)
                if is_dir:
                    if skip and os.path.normcase(child) in skip:
                        continue
                    if _is_link_dir(e, est):
                        try:
                            _remove_link_or_dir(maybe_long(child))
                        except OSError as exc:
                            errors.append((child, exc.strerror or str(exc)))
                    else:
                        stack.append((child, False))
                    continue
                if older_than is not None and est.st_mtime >= older_than:
                    continue
                try:
                    _force_remove(maybe_long(child))
                    if not eattrs & CLOUD_MASK:
                        freed += est.st_size
                    deleted += 1
                    if on_progress and deleted % 500 == 0:
                        on_progress(freed, deleted)
                except OSError as exc:
                    if len(errors) < 2000:
                        errors.append((child, exc.strerror or str(exc)))
    return freed, deleted, errors


def unique_destination(folder, name):
    target = os.path.join(folder, name)
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(name)
    for i in range(2, 10000):
        candidate = os.path.join(folder, f"{stem} ({i}){ext}")
        if not os.path.exists(candidate):
            return candidate
    raise FileExistsError(target)


def move_path(src, dest_folder):
    """Move a file/folder into dest_folder (across drives too). Returns the new path."""
    os.makedirs(dest_folder, exist_ok=True)
    target = unique_destination(dest_folder, os.path.basename(src.rstrip("\\/")))
    shutil.move(src, target)
    return target


def replace_with_hardlink(keep, target, expected_size=None, expected_mtime=None):
    """Replace ``target`` with a hard link to ``keep`` (same volume only)."""
    if os.path.splitdrive(os.path.abspath(keep))[0].lower() != os.path.splitdrive(os.path.abspath(target))[0].lower():
        raise OSError("Hard links only work on the same drive")
    st_keep = os.stat(keep)
    st_target = os.stat(target)
    if st_keep.st_size != st_target.st_size or (expected_size is not None and st_target.st_size != expected_size):
        raise OSError("File changed since the duplicate search")
    if expected_mtime is not None and int(st_target.st_mtime) != int(expected_mtime):
        raise OSError("File was modified since the duplicate search")
    if (st_keep.st_dev, st_keep.st_ino) == (st_target.st_dev, st_target.st_ino):
        return 0
    tmp = target + f".spacehound-{int(time.time() * 1000)}.tmp"
    os.link(keep, tmp)
    try:
        os.replace(tmp, target)
    except OSError:
        os.remove(tmp)
        raise
    return st_target.st_size
