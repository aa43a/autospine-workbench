"""Lossless bounded chunks for large references; legacy flat bytes stay unchanged."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes

SCHEMA = 'autospine.character-reference-chunks/v1'
COMPRESSED_SCHEMA = 'autospine.character-reference-chunks/v2'


def carry_setup(source, output):
    """Carry an exact setup reference only through an unchanged bind structure."""
    key = 'rig-setup-reference.json'
    if key not in source:
        return None
    value = json.loads(source[key])
    if value['skeleton_sha256'] != sha256(source['skeleton.json']).hexdigest():
        raise ValueError('character_setup_source_mismatch')
    before, after = (json.loads(p['skeleton.json']) for p in (source, output))
    if any(before.get(k) != after.get(k) for k in ('bones', 'slots', 'skins')):
        raise ValueError('character_setup_bind_changed')
    value['skeleton_sha256'] = sha256(output['skeleton.json']).hexdigest()
    output[key] = canonical_bytes(value)
    return value['vertices']


def read(files):
    value = json.loads(files['numeric-reference.json'])
    if 'schema' not in value:
        return value
    if value['schema'] not in (SCHEMA, COMPRESSED_SCHEMA) or not value.get('chunks') or len(value['chunks']) > 1024:
        raise ValueError('character_reference_chunks_invalid')
    animations = {}; counts = {}; decoded_size = 0
    for row in value['chunks']:
        digest = row['sha256']; name = row['animation']
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest) \
                or row['file'] != 'numeric-reference/'+digest+'.json' or row['part'] != counts.get(name, 0):
            raise ValueError('character_reference_chunk_identity')
        raw = files[row['file']]
        if sha256(raw).hexdigest() != digest:
            raise ValueError('character_reference_chunk_identity')
        if value['schema'] == COMPRESSED_SCHEMA:
            from .reference_chunk_codec import decode
            raw = decode(raw)
            decoded_size += len(raw)
            if decoded_size > 256 << 20:
                raise ValueError('character_reference_decoded_limit')
        frames = json.loads(raw)
        if not isinstance(frames, list) or not frames or len(frames) > 128:
            raise ValueError('character_reference_chunk_frames')
        animations.setdefault(name, []).extend(frames); counts[name] = row['part']+1
    return dict(skeleton_sha256=value['skeleton_sha256'], animations=animations)


def write(files, reference, limit=64 << 20, *, compressed=False):
    result = {n: raw for n, raw in files.items() if not n.startswith('numeric-reference/')}
    raw = canonical_bytes(reference)
    if compressed and len(raw) > 256 << 20:
        raise ValueError('character_reference_decoded_limit')
    if len(raw) <= limit and not compressed:
        result['numeric-reference.json'] = raw
        return result
    rows = []
    for name, frames in sorted(reference['animations'].items()):
        for part, start in enumerate(range(0, len(frames), 128)):
            chunk = canonical_bytes(frames[start:start+128])
            if len(chunk) > 64 << 20:
                raise ValueError('character_reference_chunk_resource_limit')
            if compressed:
                from .reference_chunk_codec import encode
                chunk = encode(chunk)
            digest = sha256(chunk).hexdigest(); path = 'numeric-reference/'+digest+'.json'
            result[path] = chunk
            rows.append(dict(animation=name, part=part, file=path, sha256=digest))
    result['numeric-reference.json'] = canonical_bytes(dict(schema=COMPRESSED_SCHEMA if compressed else SCHEMA,
        skeleton_sha256=reference['skeleton_sha256'], chunks=rows))
    return result
