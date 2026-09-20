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
from ..targets.character43.motion_clip import boundaries, clip_motion, clip_animation

ANIMATION = 'external-motion'


def build_candidate(files, motion, bvh, mapping, *, character_digest, motion_digest, kimodo=None,
                    contact_correction=True, clip_bounds=None, inferred_contact_profile=None):
    """Only the animation changes; layers, meshes, weights and texture pixels stay exact."""
    source = json.loads(files['skeleton.json'])
    original = deepcopy(source)
    source['animations'] = {}
    setup_vertices = None
    if clip_bounds:
        setup = deepcopy(source)
        setup['animations'] = {ANIMATION: {'bones': {}}}
        setup_vertices = sample(setup, ANIMATION, 0)[0]
    document, evidence = build(source, motion, ANIMATION)
    original_motion = motion
    motion = clip_motion(motion, clip_bounds)
    time_range = tuple(t/1_000_000 for t in clip_bounds) if clip_bounds else None
    issues = []
    from ..targets.character43.projected_lengths import build as add_lengths
    try:
        if kimodo is None:
            document, lengths = add_lengths(document, ANIMATION, bvh, mapping, time_range=time_range)
        else:
            from ..targets.character43.kimodo_lengths import build as add_npz_lengths
            document, lengths = add_npz_lengths(document, ANIMATION, *kimodo, mapping, time_range=time_range)
        evidence['projected_lengths'] = lengths
    except ValueError as exc:
        # Preserve a diagnostic rotation-only animation when projection is unsuitable.
        # It must not become a supported/adopted result by falling back silently.
        issues.append(dict(stage='projection', reason_code=str(exc)))
    document = clip_animation(document, ANIMATION, clip_bounds)
    if clip_bounds:
        evidence['clip'] = dict(start_tick=clip_bounds[0], end_tick=clip_bounds[1],
                                source_duration_ticks=original_motion['duration_ticks'],
                                pose_policy='preserve_original_setup_relative_values')
    from ..targets.character43.affine_area_repair import repair
    try:
        document, correction = repair(document, ANIMATION, samples=129, convergent=True, setup_vertices=setup_vertices)
        evidence['area_repair'] = correction
    except ValueError as exc:
        issues.append(dict(stage='repair', reason_code=str(exc)))
    duration = motion['duration_ticks'] / motion['ticks_per_second']
    key_times = {key['tick'] / motion['ticks_per_second'] for track in motion['tracks'] for key in track['keys']}
    times = sorted(key_times | {duration * i / 256 for i in range(257)})
    if len(times) > 1025 or duration <= 0:
        raise ValueError('motion_target_sample_limit')
    from ..targets.character43.motion_contacts import apply as apply_contacts
    document, contact = apply_contacts(document, ANIMATION, motion, times,
                                       evidence['reference_length_px'], enabled=contact_correction)
    if inferred_contact_profile and bvh is not None and not any(m['kind'] == 'contact' for m in original_motion['markers']):
        from ..targets.character43.inferred_contacts import measure
        from ..motion2d.contact_candidate import infer
        document, contact = measure(document, ANIMATION, motion, times, evidence['reference_length_px'],
                                    infer(bvh, mapping), clip_bounds=clip_bounds)
        from ..targets.character43.stationary_contact_policy import PROFILE as AUTO_PROFILE, select
        if inferred_contact_profile == AUTO_PROFILE:
            document, contact = select(document, ANIMATION, motion, times, evidence['reference_length_px'],
                                       contact, bvh, mapping, enabled=contact_correction, clip_bounds=clip_bounds)
    if contact['status'] == 'inferred_proxy_drift':
        issues.append(dict(stage='contact', reason_code='motion_inferred_contact_drift'))
    if contact['status'] == 'needs_changes':
        issues.append(dict(stage='contact', reason_code='motion_contact_drift_needs_changes'))
    if contact['selected']:
        times = sorted(set(times) | {k['time'] for k in document['animations'][ANIMATION]['bones']['root']['translate']})
        if contact['status'] == 'inferred_proxy_corrected':
            times = sorted(set(times) | {s['time'] for r in contact['after']['intervals'] for s in r['samples']})
    frames = [dict(time=t, vertices=sample(document, ANIMATION, t)[0]) for t in times]
    raw = canonical_bytes(document)
    result = {name: data for name, data in files.items() if name.endswith('.png') or name == 'skeleton.atlas'}
    result['skeleton.json'] = raw
    if setup_vertices is not None:
        result['rig-setup-reference.json'] = canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(),
                                                                 time=0, vertices=setup_vertices))
    result = write_reference(result, dict(skeleton_sha256=sha256(raw).hexdigest(), animations={ANIMATION: frames}))
    geometry = inspect(result, setup_vertices=setup_vertices)
    if not geometry['passed']:
        issues.append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    if {k: v for k, v in document.items() if k != 'animations'} != {k: v for k, v in original.items() if k != 'animations'}:
        raise ValueError('motion_target_rig_changed')
    evidence.update(character_sha256=character_digest, motion_bundle_sha256=motion_digest,
                    geometry_passed=geometry['passed'], issues=issues,
                    contact_status=contact['status'], contact_policy=contact['policy_id'],
                    depth_order_status='not_evaluated',
                    runtime_status='not_evaluated', authority='none',
                    status='needs_changes' if issues else 'needs_review')
    result.update({'motion-review.json': canonical_bytes(evidence),
                   'motion-contact.json': canonical_bytes(contact),
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
    from ..targets.character43.runtime_storage_reference import PROFILE
    storage_reference = request.get('runtime_reference_profile')
    if storage_reference not in (None, PROFILE):
        raise ValueError('motion_runtime_reference_profile_unsupported')
    from ..targets.character43.inferred_contacts import PROFILE as CONTACT_PROFILE
    inferred_profile = request.get('inferred_contact_profile')
    from ..targets.character43.stationary_contact_policy import PROFILE as AUTO_PROFILE
    if inferred_profile not in (None, CONTACT_PROFILE, AUTO_PROFILE):
        raise ValueError('motion_inferred_contact_profile_unsupported')
    store = AnimatedStore(state_root)
    progress(folder, 'retarget')
    motion_id = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state_root).load(motion_id['clip_sha256'], motion_id['bundle_sha256'])
    motion = json.loads((bundle.path / 'motion.json').read_bytes())
    kimodo = (bundle.raw_npz, bundle.kimodo_source) if bundle.source_kind == 'kimodo_npz' else None
    bvh = None if kimodo else parse_bvh((bundle.path / 'source.bvh').read_bytes())
    from ..bvh_fk import bvh_frame_ticks
    from ..kimodo_npz_projection import kimodo_frame_ticks
    ticks = kimodo_frame_ticks(bundle.kimodo_source) if kimodo else bvh_frame_ticks(bvh)
    clip_bounds = boundaries(request.get('clip'), ticks)
    if max(len(track['keys']) for track in clip_motion(motion, clip_bounds)['tracks']) > 768:
        raise ValueError('motion_target_sample_limit')
    files, evidence, geometry = build_candidate(store.read(request['character_sha256']), motion,
        bvh, json.loads((bundle.path / 'map.json').read_bytes()), kimodo=kimodo,
        contact_correction=request.get('contact_correction', True),
        inferred_contact_profile=inferred_profile,
        clip_bounds=clip_bounds,
        character_digest=request['character_sha256'], motion_digest=motion_id['bundle_sha256'])
    progress(folder, 'publish_candidate')
    digest = store.publish(files)
    runtime = capture(SimpleNamespace(workspace_root=workspace), store, digest, folder,
                      progress=lambda stage: progress(folder, 'runtime'), cancel_requested=lambda: False,
                      storage_reference=storage_reference == PROFILE)
    result = dict(artifact_sha256=digest, character_animation_status=evidence['status'], runtime=runtime,
                  animations=[ANIMATION], issues=evidence['issues'],
                  geometry_passed=geometry['passed'], contact_status=evidence['contact_status'],
                  clip=request.get('clip'),
                  runtime_reference_profile=storage_reference or 'legacy_ideal_reference',
                  inferred_contact_profile=inferred_profile,
                  depth_order_status='not_evaluated', authority='none', production_authorized=False)
    (folder / 'worker-result.json').write_bytes(canonical_bytes(result))


if __name__ == '__main__':
    try:
        execute(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except Exception as exc:
        print(json.dumps(dict(reason_code=str(exc)[:200])))
        sys.exit(1)
