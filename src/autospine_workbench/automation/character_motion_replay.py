"""Replay exact motion when only the upstream build receipt address changed."""
from copy import deepcopy
from hashlib import sha256
import json

from .storage_io import canonical_bytes
from .pipeline_run import PipelineRunError


def equivalent(previous, current):
    """Every render/evidence byte and every other manifest field must match."""
    if {k:v for k,v in previous.items() if k != 'character-manifest.json'} != {
            k:v for k,v in current.items() if k != 'character-manifest.json'}:
        return False
    manifests = [json.loads(source['character-manifest.json']) for source in (previous, current)]
    for manifest in manifests:
        sources = manifest.get('source_addresses', {})
        address = sources.pop('base_bundle_sha256', None)
        if not isinstance(address, str) or len(address) != 64:
            return False
    return manifests[0] == manifests[1]


def replay(store, previous_digest, current_digest, motion_digest):
    from ..targets.character43.motion_composition import compose
    try:
        previous, current = store.read(previous_digest), store.read(current_digest)
    except (KeyError, ValueError, OSError) as exc:
        raise PipelineRunError('character_motion_source_changed') from exc
    if not equivalent(previous, current):
        raise PipelineRunError('character_motion_source_changed')
    files = compose(previous, store.read(motion_digest), previous_digest, motion_digest)
    manifest = json.loads(files['character-manifest.json'])
    manifest['source_addresses'] = deepcopy(json.loads(current['character-manifest.json'])['source_addresses'])
    receipt = dict(schema='autospine.character-motion-replay/v1', authority='none',
        previous_character_sha256=previous_digest, current_character_sha256=current_digest,
        motion_candidate_sha256=motion_digest, rule='identical-files-and-manifest-except-base-bundle-v1')
    files['motion-replay.json'] = canonical_bytes(receipt)
    manifest['motion_replay_sha256'] = sha256(files['motion-replay.json']).hexdigest()
    manifest['files'] = {k:sha256(v).hexdigest() for k,v in files.items() if k != 'character-manifest.json'}
    files['character-manifest.json'] = canonical_bytes(manifest)
    return files
