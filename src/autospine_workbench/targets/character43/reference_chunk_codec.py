"""Lossless JSON envelope for bounded numeric-reference chunks, not Spine assets."""
import base64
import gzip
from hashlib import sha256
from io import BytesIO
import json
import zlib

from ...automation.storage_io import canonical_bytes

LIMIT = 64 << 20
CODEC = 'gzip-base64-json-v1'


def encode(raw):
    if len(raw) > LIMIT: raise ValueError('character_reference_chunk_resource_limit')
    return canonical_bytes(dict(codec=CODEC, bytes=len(raw), sha256=sha256(raw).hexdigest(),
        data=base64.b64encode(gzip.compress(raw, compresslevel=6, mtime=0)).decode('ascii')))


def decode(raw):
    try:
        value = json.loads(raw)
        if (set(value) != {'codec', 'bytes', 'sha256', 'data'} or value['codec'] != CODEC
                or type(value['bytes']) is not int or not 0 < value['bytes'] <= LIMIT):
            raise ValueError('invalid envelope')
        compressed = base64.b64decode(value['data'], validate=True)
        if len(compressed) > LIMIT: raise ValueError('compressed limit')
        with gzip.GzipFile(fileobj=BytesIO(compressed)) as handle:
            decoded = handle.read(value['bytes']+1)
        if len(decoded) != value['bytes'] or sha256(decoded).hexdigest() != value['sha256']:
            raise ValueError('decoded identity')
        return decoded
    except (ValueError, KeyError, TypeError, OSError, EOFError, zlib.error) as error:
        raise ValueError('character_reference_compressed_chunk_invalid') from error
