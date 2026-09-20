"""Isolated external-motion retargeting on an exact existing whole-character rig."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from ..bvh_parser import parse_bvh
from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..targets.character43.motionir_candidate import build, sample
from ..targets.character43.deformation_qa import inspect
from ..targets.character43.numeric_reference import write as write_reference
from .animated_store import AnimatedStore
from .character_capture import capture
from .motion_intake_process import progress
from .storage_io import canonical_bytes, read_document

ANIMATION = 'external-motion'


def build_candidate(files, motion, bvh, mapping, *, character_digest, motion_digest):
    """Only the animation changes; layers, meshes, weights and texture pixels stay exact."""
    source = json.loads(files['skeleton.json'])
    original = deepcopy(source)
    source['animations'] = {}
    document, evidence = build(source, motion, ANIMATION)
    issues = []
    from ..targets.character43.projected_lengths import build as add_lengths
    try:
        document, lengths = add_lengths(document, ANIMATION, bvh, mapping)
        evidence['projected_lengths'] = lengths
    except ValueError as exc:
        # Preserve a diagnostic rotation-only animation when projection is unsuitable.
        # It must not become a supported/adopted result by falling back silently.
        issues.append(dict(stage='projection', reason_code=str(exc)))
    from ..targets.character43.affine_area_repair import repair
    try:
        document, correction = repair(document, ANIMATION, samples=129, convergent=True)
        evidence['area_repair'] = correction
    except ValueError as exc:
        issues.append(dict(stage='repair', reason_code=str(exc)))
    duration = motion['duration_ticks'] / motion['ticks_per_second']
    key_times = {key['tick'] / motion['ticks_per_second'] for track in motion['tracks'] for key in track['keys']}
    times = sorted(key_times | {duration * i / 256 for i in range(257)})
    if len(times) > 1025 or duration <= 0:
        raise ValueError('motion_target_sample_limit')
    frames = [dict(time=t, vertices=sample(document, ANIMATION, t)[0]) for t in times]
    raw = canonical_bytes(document)
    result = {name: data for name, data in files.items() if name.endswith('.png') or name == 'skeleton.atlas'}
    result['skeleton.json'] = raw
    result = write_reference(result, dict(skeleton_sha256=sha256(raw).hexdigest(), animations={ANIMATION: frames}))
    geometry = inspect(result)
    if not geometry['passed']:
        issues.append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    if {k: v for k, v in document.items() if k != 'animations'} != {k: v for k, v in original.items() if k != 'animations'}:
        raise ValueError('motion_target_rig_changed')
    evidence.update(character_sha256=character_digest, motion_bundle_sha256=motion_digest,
                    geometry_passed=geometry['passed'], issues=issues,
                    contact_status='not_evaluated', depth_order_status='not_evaluated',
                    runtime_status='not_evaluated', authority='none',
                    status='needs_changes' if issues else 'needs_review')
    result.update({'motion-review.json': canonical_bytes(evidence),
                   'motion-ir.json': canonical_bytes(motion), 'deformation.json': canonical_bytes(geometry)})
    source_manifest = json.loads(files['character-manifest.json'])
    manifest = dict(schema='autospine.character-motion-preview/v1', profile='external-motion-target-v1',
                    authority='none', production_authorized=False, animations=[ANIMATION],
                    source_character_sha256=character_digest, source_motion_bundle_sha256=motion_digest,
                    source_addresses=source_manifest['source_addresses'], layers=source_manifest['layers'],
                    status=evidence['status'], files={name: sha256(data).hexdigest() for name, data in result.items()})
    result['character-manifest.json'] = canonical_bytes(manifest)
    return result, evidence, geometry


def execute(folder, state_root, workspace):
    request = read_document(folder / 'request.json')
    store = AnimatedStore(state_root)
    progress(folder, 'retarget')
    motion_id = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state_root).load(motion_id['clip_sha256'], motion_id['bundle_sha256'])
    motion = json.loads((bundle.path / 'motion.json').read_bytes())
    # Bound expensive correction work before allocating a full character timeline.
    if max(len(track['keys']) for track in motion['tracks']) > 768:
        raise ValueError('motion_target_sample_limit')
    files, evidence, geometry = build_candidate(store.read(request['character_sha256']), motion,
        parse_bvh((bundle.path / 'source.bvh').read_bytes()), json.loads((bundle.path / 'map.json').read_bytes()),
        character_digest=request['character_sha256'], motion_digest=motion_id['bundle_sha256'])
    progress(folder, 'publish_candidate')
    digest = store.publish(files)
    runtime = capture(SimpleNamespace(workspace_root=workspace), store, digest, folder,
                      progress=lambda stage: progress(folder, 'runtime'), cancel_requested=lambda: False)
    result = dict(artifact_sha256=digest, character_animation_status=evidence['status'], runtime=runtime,
                  animations=[ANIMATION], issues=evidence['issues'],
                  geometry_passed=geometry['passed'], contact_status='not_evaluated',
                  depth_order_status='not_evaluated', authority='none', production_authorized=False)
    (folder / 'worker-result.json').write_bytes(canonical_bytes(result))


if __name__ == '__main__':
    try:
        execute(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except Exception as exc:
        print(json.dumps(dict(reason_code=str(exc)[:200])))
        sys.exit(1)
