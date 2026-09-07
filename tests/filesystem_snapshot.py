"""Strict evidence snapshots with metadata for the Windows owner lock."""

from pathlib import Path


def snapshot_file(root: Path, path: Path):
    # Windows denies byte reads of the manager's lifetime-locked byte. Keep
    # tracking its identity and writes while snapshotting every artifact byte.
    owner_lock = "jobs/body-sway-spine42-v3-runtime-manager-owner-v2/owner.lock"
    if path.relative_to(root).as_posix() == owner_lock:
        info = path.lstat()
        return ("owner-lock", info.st_dev, info.st_ino, info.st_mode,
                info.st_nlink, info.st_size, info.st_mtime_ns)
    return path.read_bytes()
