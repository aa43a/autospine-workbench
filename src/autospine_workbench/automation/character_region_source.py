"""Recover the exact pre-motion review source by replaying immutable compositions."""
import json
from ..targets.character43.motion_composition import compose


def resolve(store, digest, files):
    seen = set()
    while json.loads(files['character-manifest.json']).get('profile') == 'exact-character-motion-composition-v1':
        if digest in seen or len(seen) >= 16:
            raise ValueError('character_region_composition_lineage')
        seen.add(digest)
        manifest = json.loads(files['character-manifest.json'])
        row = manifest['motion_compositions'][-1]
        base_digest = row['source_character_sha256']
        motion_digest = row['motion_candidate_sha256']
        base = store.read(base_digest)
        motion = store.read(motion_digest)
        if compose(base, motion, base_digest, motion_digest) != files:
            raise ValueError('character_region_composition_lineage')
        digest, files = base_digest, base
    return digest, files
