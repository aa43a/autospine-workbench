"""Strict inline, content-addressed replacement for the optional mouth template."""
from base64 import b64decode, b64encode
from hashlib import sha256
import binascii
import re
import struct
import zlib

from ...png_rgba import decode_rgba_png

MAX_BYTES = 32768
WIDTH, HEIGHT = 64, 48
PREFIX = 'joint_face_mouth_template_image_'


def _png(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(PREFIX+'png')
    position = 8; chunks = []; compressed = bytearray(); idat_closed = False
    while position + 12 <= len(data):
        length = struct.unpack('>I', data[position:position+4])[0]
        kind = data[position+4:position+8]; end = position+12+length
        if end > len(data) or not re.fullmatch(b'[A-Za-z]{4}', kind):
            raise ValueError(PREFIX+'png')
        payload = data[position+8:end-4]
        crc = struct.unpack('>I', data[end-4:end])[0]
        if binascii.crc32(kind+payload) & 0xffffffff != crc:
            raise ValueError(PREFIX+'crc')
        if not chunks and kind != b'IHDR':
            raise ValueError(PREFIX+'png')
        if kind in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError(PREFIX+'animated')
        if not kind[0] & 32 and kind not in (b'IHDR', b'PLTE', b'IDAT', b'IEND'):
            raise ValueError(PREFIX+'png')
        if kind == b'IHDR':
            if chunks or len(payload) != 13:
                raise ValueError(PREFIX+'png')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (width, height) != (WIDTH, HEIGHT):
                raise ValueError(PREFIX+'dimensions')
            if (depth, color, compression, filtering, interlace) != (8, 6, 0, 0, 0):
                raise ValueError(PREFIX+'rgba8')
        elif kind == b'IDAT':
            if idat_closed:
                raise ValueError(PREFIX+'png')
            compressed.extend(payload)
        elif b'IDAT' in chunks:
            idat_closed = True
        chunks.append(kind); position = end
        if kind == b'IEND':
            if payload or position != len(data):
                raise ValueError(PREFIX+'png')
            break
    if not chunks or chunks[-1] != b'IEND' or not compressed:
        raise ValueError(PREFIX+'png')
    # Bound decompression before passing the immutable PNG to the shared reader.
    expected = HEIGHT*(WIDTH*4+1)
    try:
        decoder = zlib.decompressobj()
        filtered = decoder.decompress(bytes(compressed), expected+1)
        if (len(filtered) != expected or not decoder.eof
                or decoder.unconsumed_tail or decoder.unused_data):
            raise ValueError(PREFIX+'decoded_size')
        image = decode_rgba_png(data)
    except (ValueError, zlib.error) as error:
        raise ValueError(PREFIX+'decoded_size') from error
    alphas = image.pixels[3::4]
    if min(alphas) == 255 or max(alphas) == 0:
        raise ValueError(PREFIX+'transparency')


def normalize(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {'png_base64', 'sha256'}:
        raise ValueError(PREFIX+'fields')
    encoded, digest = value['png_base64'], value['sha256']
    if not isinstance(encoded, str) or len(encoded) > 4*((MAX_BYTES+2)//3):
        raise ValueError(PREFIX+'size')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError(PREFIX+'sha256')
    try:
        data = b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError(PREFIX+'base64') from error
    if not 1 <= len(data) <= MAX_BYTES:
        raise ValueError(PREFIX+'size')
    if b64encode(data).decode('ascii') != encoded:
        raise ValueError(PREFIX+'base64')
    if sha256(data).hexdigest() != digest:
        raise ValueError(PREFIX+'sha256')
    _png(data)
    return dict(png_base64=encoded, sha256=digest)
