"""Whole-character idle on the existing rig, independent of limb/sleeve provenance."""
from hashlib import sha256
import json
import math

from ...automation.storage_io import canonical_bytes
from ...manifest_artifacts import require_sha256
from ...motion_builtin import build_builtin_motion
from .deformation_qa import inspect
from .motionir_candidate import build, sample


def generate(files, source_digest, samples=129):
    require_sha256(source_digest, 'Character source')
    if type(samples) is not int or not 3 <= samples <= 1025:
        raise ValueError('character_idle_samples_invalid')
    motion = build_builtin_motion('idle').document
    document, evidence = build(json.loads(files['skeleton.json']), motion, 'idle')
    document['animations'] = {'idle': document['animations']['idle']}
    duration = motion['duration_ticks'] / motion['ticks_per_second']
    # Include authored key times even when the requested uniform grid misses them.
    times = sorted({duration*i/(samples-1) for i in range(samples)} | {
        k['tick']/motion['ticks_per_second'] for t in motion['tracks'] for k in t['keys']})
    frames = [dict(time=t, vertices=sample(document, 'idle', t)[0]) for t in times]
    first, last = frames[0]['vertices'], frames[-1]['vertices']
    error = max((math.dist(a, b) for slot in first
                 for a, b in zip(first[slot], last[slot], strict=True)), default=0.)
    if not math.isfinite(error) or error > 1e-7:
        raise ValueError('character_idle_loop_open')
    raw = canonical_bytes(document)
    result = {n: data for n, data in files.items() if n.endswith('.png') or n == 'skeleton.atlas'}
    result.update({'skeleton.json': raw, 'motion-ir.json': canonical_bytes(motion),
        'numeric-reference.json': canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(),
                                                       animations={'idle': frames}))})
    qa = inspect(result)
    evidence.update(profile='whole-character-builtin-idle-v1', character_sha256=source_digest,
                    geometry_passed=qa['passed'], loop_endpoint_error_px=error,
                    sample_count=len(frames), runtime_status='not_evaluated',
                    contact_status='annotation_only_not_foot_lock',
                    existing_clips='preserved_by_exact_composition_only')
    result['deformation.json'] = canonical_bytes(qa)
    result['motion-review.json'] = canonical_bytes(evidence)
    result['character-manifest.json'] = canonical_bytes(dict(
        schema='autospine.character-motion-preview/v1', profile='whole-character-builtin-idle-v1',
        authority='none', production_authorized=False, animations=['idle'],
        source_character_sha256=source_digest, status='preview_only' if qa['passed'] else 'blocked',
        files={n: sha256(data).hexdigest() for n, data in result.items()}))
    return result
