"""Exclusive staging files with bounded collision retries on all platforms."""
import errno
import os
from pathlib import Path
import secrets


def create_staging_file(directory, prefix='pending-'):
    """Return (fd, path); permission failures are never treated as collisions.

    Callers validate the staging directory and own descriptor/path cleanup.
    Python's tempfile retries PermissionError on Windows when access(W_OK)
    succeeds, which can hide a denied write for a very long time.
    """
    folder = Path(directory).absolute()
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    for _ in range(32):
        path = folder / (prefix + secrets.token_hex(16))
        try:
            return os.open(path, flags, 0o600), path
        except FileExistsError:
            continue
    raise FileExistsError(errno.EEXIST, 'Staging filename collision limit reached', str(folder))
