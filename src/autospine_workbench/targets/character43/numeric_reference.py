"""Lossless bounded chunks for large references; legacy flat bytes stay unchanged."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes

SCHEMA = 'autospine.character-reference-chunks/v1'


def read(files):
    value = json.loads(files['numeric-reference.json'])
    if 'schema' not in value:
        return value
    if value['schema'] != SCHEMA or not value.get('chunks') or len(value['chunks']) > 1024:
        raise ValueError('character_reference_chunks_invalid')
    animations = {}; counts = {}
    for row in value['chunks']:
        digest = row['sha256']; name = row['animation']
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest) \
                or row['file'] != 'numeric-reference/'+digest+'.json' or row['part'] != counts.get(name, 0):
            raise ValueError('character_reference_chunk_identity')
        raw = files[row['file']]
        if sha256(raw).hexdigest() != digest:
            raise ValueError('character_reference_chunk_identity')
        frames = json.loads(raw)
        if not isinstance(frames, list) or not frames or len(frames) > 128:
            raise ValueError('character_reference_chunk_frames')
        animations.setdefault(name, []).extend(frames); counts[name] = row['part']+1
    return dict(skeleton_sha256=value['skeleton_sha256'], animations=animations)


def write(files, reference, limit=64 << 20):
    result = {n: raw for n, raw in files.items() if not n.startswith('numeric-reference/')}
    raw = canonical_bytes(reference)
    if len(raw) <= limit:
        result['numeric-reference.json'] = raw
        return result
    rows = []
    for name, frames in sorted(reference['animations'].items()):
        for part, start in enumerate(range(0, len(frames), 128)):
            chunk = canonical_bytes(frames[start:start+128])
            if len(chunk) > 64 << 20:
                raise ValueError('character_reference_chunk_resource_limit')
            digest = sha256(chunk).hexdigest(); path = 'numeric-reference/'+digest+'.json'
            result[path] = chunk
            rows.append(dict(animation=name, part=part, file=path, sha256=digest))
    result['numeric-reference.json'] = canonical_bytes(dict(schema=SCHEMA,
        skeleton_sha256=reference['skeleton_sha256'], chunks=rows))
    return result
