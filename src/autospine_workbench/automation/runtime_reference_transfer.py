"""Bounded temporary Python-to-Node reference transport, not a published asset."""
import gzip

from .storage_io import canonical_bytes

MAX_DECODED_BYTES = 256 * 1024 * 1024
COMPRESS_AFTER_BYTES = 64 * 1024 * 1024


def write(root, reference):
    raw = canonical_bytes(reference)
    if len(raw) > MAX_DECODED_BYTES:
        raise ValueError('runtime_storage_reference_limit')
    path = root / 'runtime-storage-reference.json'
    if len(raw) > COMPRESS_AFTER_BYTES:
        path = root / 'runtime-storage-reference.json.gz'
        # These bytes are temporary IPC; the decoder verifies the full reference.
        # Low compression keeps the same content while avoiding expensive level 9.
        raw = gzip.compress(raw, compresslevel=1, mtime=0)
    path.write_bytes(raw)
    return path
