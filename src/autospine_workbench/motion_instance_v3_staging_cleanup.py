"""Lexical, alias-safe cleanup for MotionInstance v3 staging roots."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat


def remove_lexical_staging(
    path: Path,
    parent: Path,
) -> None:
    """Remove only the lexical staging entry, never its resolved target."""

    if os.name == "nt":
        _remove_windows_staging(path)
    else:
        _remove_posix_staging(path, parent)


def _remove_windows_staging(path: Path) -> None:
    """Let rmtree recheck real directories; unlink root aliases only."""

    info = path.lstat()
    if is_alias(path):
        if stat.S_ISDIR(info.st_mode):
            os.rmdir(path)
        else:
            path.unlink()
        return
    if not stat.S_ISDIR(info.st_mode):
        return
    # Since Python 3.8, Windows rmtree does not traverse directory junctions.
    # The lexical child is passed so a root swap removes only that entry.
    shutil.rmtree(path)


def _remove_posix_staging(path: Path, parent: Path) -> None:
    """Anchor recursive removal to a verified parent descriptor."""

    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        return
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    before = parent.lstat()
    descriptor = os.open(parent, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino)
            != (opened.st_dev, opened.st_ino)
            or not stat.S_ISDIR(opened.st_mode)
        ):
            return
        child = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISLNK(child.st_mode):
            os.unlink(path.name, dir_fd=descriptor)
            return
        if not stat.S_ISDIR(child.st_mode):
            return
        shutil.rmtree(path.name, dir_fd=descriptor)
    finally:
        os.close(descriptor)


def is_alias(path: Path) -> bool:
    """Treat links, junctions, reparse points, and stat failures as aliases."""

    try:
        info = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    junction = getattr(path, "is_junction", None)
    try:
        if callable(junction) and junction():
            return True
    except OSError:
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse)


__all__ = ["is_alias", "remove_lexical_staging"]
