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
from ..targets.character43.motion_depth_overlap import SPARSE_DEPTH_PROFILE

ANIMATION = 'external-motion'


def build_candidate(files, motion, bvh, mapping, *, character_digest, motion_digest, kimodo=None,
                    contact_correction=True, clip_bounds=None, inferred_contact_profile=None, depth_review_profile=None,
                    on_stage=None, oblique=None, torso_projection=None, pose_fit=None, moving_ankles=None):
    """Preserve the rig, or verify the explicit regional render transformation."""
    from ..targets.character43.regional_depth_profile import PROFILE as REGIONAL_PROFILE
    from ..targets.character43.camera_track import PROFILE as CAMERA_PROFILE
    camera=pose_fit is not None and pose_fit.get('profile')==CAMERA_PROFILE
    if camera and (contact_correction or moving_ankles is None or clip_bounds is not None or
                   torso_projection is not None or depth_review_profile==REGIONAL_PROFILE):
        raise ValueError('camera_target_requires_camera_ankles_and_full_unwarped_clip')
    if camera and (moving_ankles.get('profile')!='continuous-camera-ankle-displacement-v1' or
                   moving_ankles.get('keys')!=pose_fit.get('keys')):
        raise ValueError('camera_target_ankle_track_mismatch')
    if camera and (oblique or {}).get('sampling_profile')=='camera-world-projected-adaptive-v2':
        if (moving_ankles.get('sampling_profile')!=oblique['sampling_profile']
                or moving_ankles.get('times')!=pose_fit.get('times')):
            raise ValueError('camera_target_ankle_sampling_mismatch')
    source = json.loads(files['skeleton.json'])
    original = deepcopy(source)
    source['animations'] = {}
    setup_vertices = None
    if moving_ankles is not None or pose_fit is not None or clip_bounds or depth_review_profile in ('external-arm-torso-depth-overlap-v2', REGIONAL_PROFILE, SPARSE_DEPTH_PROFILE):
        setup = deepcopy(source)
        setup['animations'] = {ANIMATION: {'bones': {}}}
        setup_vertices = sample(setup, ANIMATION, 0)[0]
    document, evidence = build(source, motion, ANIMATION)
    if oblique is not None:
        evidence['oblique_projection'] = oblique
    original_motion = motion
    motion = clip_motion(motion, clip_bounds)
    time_range = tuple(t/1_000_000 for t in clip_bounds) if clip_bounds else None
    issues = []
    from .motion_target_pose import project as project_pose, correct as correct_pose, final_times
    try:
        document, lengths = project_pose(document, ANIMATION, original_motion, bvh, mapping, kimodo,
                                         oblique, time_range, pose_fit)
        evidence['source_pose_fit' if pose_fit is not None else 'projected_lengths'] = lengths
        if pose_fit is not None:
            evidence['profile'] = lengths['target_profile']
            if any(row.get('unreliable_frames') for row in lengths.get('records', [])):
                issues.append(dict(stage='projection', reason_code='motion_source_pose_direction_unreliable'))
            if camera and pose_fit.get('surface_issues'):
                issues.append(dict(stage='projection',reason_code='motion_camera_side_rear_surface_unverified'))
    except ValueError as exc:
        if pose_fit is not None:
            raise
        # Preserve a diagnostic rotation-only animation when projection is unsuitable.
        # It must not become a supported/adopted result by falling back silently.
        issues.append(dict(stage='projection', reason_code=str(exc)))
    document = clip_animation(document, ANIMATION, clip_bounds)
    if clip_bounds:
        evidence['clip'] = dict(start_tick=clip_bounds[0], end_tick=clip_bounds[1],
                                source_duration_ticks=original_motion['duration_ticks'],
                                pose_policy='preserve_original_setup_relative_values')
    try:
        document, correction = correct_pose(document, ANIMATION, setup_vertices, pose_fit,
                                             **({'on_stage':on_stage} if on_stage else {}))
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
    if camera:
        from ..targets.character43.camera_contact import build as camera_contact
        hypothesis=None
        if inferred_contact_profile and bvh is not None and not any(m['kind']=='contact' for m in original_motion['markers']):
            from ..motion2d.contact_candidate import infer
            hypothesis=infer(bvh,mapping,source_up='+Y')
        contact=camera_contact(document,ANIMATION,motion,moving_ankles,times,evidence['reference_length_px'],hypothesis=hypothesis)
    if not camera and inferred_contact_profile and bvh is not None and not any(m['kind'] == 'contact' for m in original_motion['markers']):
        from ..targets.character43.inferred_contacts import measure
        from ..motion2d.contact_candidate import infer
        from ..targets.character43.stationary_contact_policy import PROFILE as AUTO_PROFILE, LEGACY_PROFILE, select
        from ..targets.character43.phase_contact_policy import PROFILE as PHASE_PROFILE, select as select_phase
        document, contact = measure(document, ANIMATION, motion, times, evidence['reference_length_px'],
                                    infer(bvh, mapping, source_up='+Y' if inferred_contact_profile in (AUTO_PROFILE, PHASE_PROFILE) else None), clip_bounds=clip_bounds)
        if inferred_contact_profile == PHASE_PROFILE:
            document, contact = select_phase(document, ANIMATION, motion, times, evidence['reference_length_px'],
                                             contact, bvh, mapping, enabled=contact_correction,
                                             clip_bounds=clip_bounds, setup_vertices=setup_vertices)
        if inferred_contact_profile in (AUTO_PROFILE, LEGACY_PROFILE):
            document, contact = select(document, ANIMATION, motion, times, evidence['reference_length_px'],
                                       contact, bvh, mapping, enabled=contact_correction, clip_bounds=clip_bounds,
                                       profile=inferred_contact_profile)
    if pose_fit is not None and pose_fit.get('post_contact_profile'):
        from .motion_post_contact import apply as repair_after_contact
        document, contact, times, repair_issues = repair_after_contact(document, ANIMATION, motion,
            setup_vertices, evidence, contact, times, pose_fit, on_stage)
        evidence['profile'] = pose_fit['post_contact_profile']
        issues.extend(repair_issues)
    if contact['status'] == 'inferred_proxy_drift':
        issues.append(dict(stage='contact', reason_code='motion_inferred_contact_drift'))
    if contact['status'] == 'needs_changes':
        issues.append(dict(stage='contact', reason_code='motion_contact_drift_needs_changes'))
    if contact['status'] == 'inferred_partial_corrected':
        issues.append(dict(stage='contact', reason_code='motion_source_contact_intervals_unverified'))
    if contact['selected']:
        times = sorted(set(times) | {k['time'] for k in document['animations'][ANIMATION]['bones']['root']['translate']})
        if contact['status'] == 'inferred_proxy_corrected':
            times = sorted(set(times) | {s['time'] for r in contact['after']['intervals'] for s in r['samples']})
        if contact.get('phase_checked_times'):
            times = sorted(set(times) | set(contact['phase_checked_times']))
    depth = None
    torso_evidence = None
    if torso_projection is not None:
        if depth_review_profile not in ('external-arm-torso-depth-overlap-v2', SPARSE_DEPTH_PROFILE):
            raise ValueError('motion_torso_requires_overlap_depth')
        from ..targets.character43.torso_projection_profile import apply as apply_torso
        if on_stage:on_stage('torso_projection')
        document, torso_evidence, reason = apply_torso(document, ANIMATION, torso_projection, times)
        if reason:
            issues.append(dict(stage='projection' if not torso_evidence['applied'] else 'contact',reason_code=reason))
        contact['torso_projection_recheck'] = torso_evidence.get('contact_preservation')
        if torso_evidence['applied'] and reason:
            contact['original_ankle_status'] = contact['status']
            contact['status'] = ('needs_changes' if torso_evidence['contact_preservation']['status']=='foot_surface_changed'
                                 else 'torso_contact_unmeasured')
        times = sorted(set(times) | {k['time'] for slots in document['animations'][ANIMATION].get('attachments',{}).values()
            for choices in slots.values() for props in choices.values() for keys in props.values() for k in keys})
        if len(times)>2049:raise ValueError('motion_torso_sample_limit')
    moving_report = None
    if moving_ankles is not None:
        from .motion_moving_ankles import apply as move_ankles
        if on_stage: on_stage('retarget')
        document, moving_report = move_ankles(document, ANIMATION, original_motion, moving_ankles,
            times, evidence['reference_length_px'], bundle_sha256=motion_digest,
            oblique=oblique, clip_bounds=clip_bounds)
        if not moving_report['applied']:
            issues.append(dict(stage='contact', reason_code='motion_moving_ankle_infeasible'))
    regional_transform = None
    depth_status = 'not_evaluated'
    if depth_review_profile:
        from ..targets.character43.motion_depth import PROFILE as DEPTH_PROFILE, OVERLAP_PROFILE, build as inspect_depth
        if depth_review_profile not in (DEPTH_PROFILE, OVERLAP_PROFILE, REGIONAL_PROFILE, SPARSE_DEPTH_PROFILE):
            raise ValueError('motion_depth_profile_unsupported')
        options = dict(camera_keys=oblique['keys'],sampling_profile=oblique.get('sampling_profile')) if camera else dict(yaw_degrees=oblique['yaw_degrees']) if oblique is not None else {}
        if camera and oblique.get('sampling_profile')=='camera-world-projected-adaptive-v2':
            options['sample_times']=pose_fit['times']
        depth = inspect_depth(document, bvh, mapping, kimodo=kimodo, clip_bounds=clip_bounds, **options)
        if depth_review_profile == REGIONAL_PROFILE:
            from ..targets.character43.regional_depth_profile import apply, remap_setup
            if on_stage:
                on_stage('depth_overlap')
            document, depth, regional_transform = apply(document, files, ANIMATION, depth, bvh, mapping,
                yaw=oblique['yaw_degrees'] if oblique is not None else 0, on_stage=on_stage, kimodo=kimodo)
            if regional_transform:
                partition = depth['regional']['partition']
                setup_vertices = remap_setup(setup_vertices, partition)
                from ..targets.character43.depth_region_partition import build as partition_build
                original['animations'] = {}
                if regional_transform['partition_slots']:
                    original = partition_build(original, regional_transform['partition_slots'])[0]
                times = sorted(set(times) | {r['time'] for r in depth['order']['frames']})
        if depth_review_profile in (OVERLAP_PROFILE, SPARSE_DEPTH_PROFILE):
            if on_stage:
                on_stage('depth_overlap')
            from ..targets.character43.motion_depth_overlap import inspect as overlap
            from ..targets.character43.motion_depth_order import build as order_candidate
            options = dict(sparse=True) if depth_review_profile == SPARSE_DEPTH_PROFILE else {}
            depth, probe = overlap(document, files, ANIMATION, depth, **options)
            proposed, order = order_candidate(document, ANIMATION, depth, probe)
            depth.update(profile=depth_review_profile, order=order)
            if proposed is not None and order['frames']:
                document = proposed
                depth['selected'] = True
                depth['status'] = 'depth_order_sampled_candidate'
                times = sorted(set(times) | {r['time'] for r in order['frames']})
            elif proposed is not None:
                depth['status'] = 'depth_overlap_no_change'
        depth_status = depth['status']
    if pose_fit is not None or moving_report is not None:
        times = final_times(document, ANIMATION, times)
    if moving_report is not None:
        from .motion_moving_ankles import check as check_ankles
        moving_report['final_check'] = check_ankles(document, ANIMATION, moving_report, times, evidence['reference_length_px'])
        if not moving_report['final_check']['passed']:
            issues.append(dict(stage='contact', reason_code='motion_moving_ankle_tracking_failed'))
        evidence['moving_ankles'] = moving_report
    if moving_report is not None or (pose_fit is not None and pose_fit.get('post_contact_profile')):
        from ..targets.character43.final_motion_contact import recheck
        contact = recheck(document, ANIMATION, motion, contact, times, evidence['reference_length_px'])
        from .motion_contact_issues import reconcile
        issues, resolved = reconcile(issues, contact, document)
        if resolved:
            evidence['resolved_issues'] = resolved
        if contact['after']['passed'] is False:
            issues.append(dict(stage='contact', reason_code='motion_final_contact_drift'))
    frames = [dict(time=t, vertices=sample(document, ANIMATION, t)[0]) for t in times]
    raw = canonical_bytes(document)
    result = {name: data for name, data in files.items() if name.endswith('.png') or name == 'skeleton.atlas'}
    result['skeleton.json'] = raw
    if moving_report is not None:
        result['motion-moving-ankles.json'] = canonical_bytes(moving_report)
    if torso_evidence is not None:
        torso_evidence.update(skeleton_sha256=sha256(raw).hexdigest(),character_sha256=character_digest,motion_bundle_sha256=motion_digest)
        result['motion-torso-projection.json'] = canonical_bytes(torso_evidence)
    if regional_transform is not None:
        result['motion-regional-transform.json'] = canonical_bytes(regional_transform)
    if oblique is not None:
        result['motion-projection.json'] = canonical_bytes(oblique)
    if setup_vertices is not None:
        result['rig-setup-reference.json'] = canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(),
                                                                 time=0, vertices=setup_vertices))
    result = write_reference(result, dict(skeleton_sha256=sha256(raw).hexdigest(), animations={ANIMATION: frames}))
    geometry = inspect(result, setup_vertices=setup_vertices)
    if pose_fit is not None:
        from ..targets.character43.geometry_repair_limits import annotate
        geometry = annotate(result, geometry, setup_vertices)
    if not geometry['passed']:
        issues.append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    if {k: v for k, v in document.items() if k != 'animations'} != {k: v for k, v in original.items() if k != 'animations'}:
        raise ValueError('motion_target_rig_changed')
    if depth is not None:
        depth.update(character_sha256=character_digest, motion_bundle_sha256=motion_digest,
                     skeleton_sha256=sha256(raw).hexdigest())
        if (depth.get('order', {}).get('failures')
                or depth.get('target_overlap', {}).get('ambiguous_visible_pair_samples')):
            issues.append(dict(stage='depth', reason_code='motion_visible_depth_needs_changes'))
        result['motion-depth.json'] = canonical_bytes(depth)
    evidence.update(character_sha256=character_digest, motion_bundle_sha256=motion_digest,
                    geometry_passed=geometry['passed'], issues=issues,
                    contact_status=contact['status'], contact_policy=contact['policy_id'],
                    depth_order_status=depth_status,
                    runtime_status='not_evaluated', authority='none',
                    status='needs_changes' if issues else 'needs_review')
    result.update({'motion-review.json': canonical_bytes(evidence),
                   'motion-contact.json': canonical_bytes(contact),
                   'motion-ir.json': canonical_bytes(motion), 'deformation.json': canonical_bytes(geometry)})
    source_manifest = json.loads(files['character-manifest.json'])
    manifest = dict(schema='autospine.character-motion-preview/v1', profile='external-motion-target-v1' if pose_fit is None else 'external-source-pose-target-v1',
                    authority='none', production_authorized=False, animations=[ANIMATION],
                    source_character_sha256=character_digest, source_motion_bundle_sha256=motion_digest,
                    source_addresses=source_manifest['source_addresses'], layers=source_manifest['layers'],
                    status=evidence['status'], files={name: sha256(data).hexdigest() for name, data in result.items()})
    result['character-manifest.json'] = canonical_bytes(manifest)
    return result, evidence, geometry


def execute(folder, state_root, workspace):
    request = read_document(folder / 'request.json')
    if request.get('repair_execution'):
        from .motion_repair_worker import execute as execute_repair
        return execute_repair(folder,state_root,workspace,request)
    from ..targets.character43.runtime_storage_reference import PROFILE
    storage_reference = request.get('runtime_reference_profile')
    if storage_reference not in (None, PROFILE):
        raise ValueError('motion_runtime_reference_profile_unsupported')
    from ..targets.character43.inferred_contacts import PROFILE as CONTACT_PROFILE
    inferred_profile = request.get('inferred_contact_profile')
    from ..targets.character43.stationary_contact_policy import PROFILE as AUTO_PROFILE, LEGACY_PROFILE
    from ..targets.character43.phase_contact_policy import PROFILE as PHASE_PROFILE
    if inferred_profile not in (None, CONTACT_PROFILE, AUTO_PROFILE, LEGACY_PROFILE, PHASE_PROFILE):
        raise ValueError('motion_inferred_contact_profile_unsupported')
    store = AnimatedStore(state_root)
    progress(folder, 'retarget')
    motion_id = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state_root).load(motion_id['clip_sha256'], motion_id['bundle_sha256'])
    from .motion_pose_policy import prepare_inputs
    motion, oblique, pose_fit = prepare_inputs(bundle, request)
    from .motion_ankle_policy import prepare as prepare_ankles
    moving_ankles = prepare_ankles(bundle, request)
    kimodo = (bundle.raw_npz, bundle.kimodo_source) if bundle.source_kind == 'kimodo_npz' else None
    bvh = None if kimodo else parse_bvh(bundle.raw_bvh)
    from ..bvh_fk import bvh_frame_ticks
    from ..kimodo_npz_projection import kimodo_frame_ticks
    ticks = kimodo_frame_ticks(bundle.kimodo_source) if kimodo else bvh_frame_ticks(bvh)
    clip_bounds = boundaries(request.get('clip'), ticks)
    if max(len(track['keys']) for track in clip_motion(motion, clip_bounds)['tracks']) > 768:
        raise ValueError('motion_target_sample_limit')
    torso_projection = None
    if request.get('torso_projection_profile') is not None:
        from ..targets.character43.torso_projection_profile import prepare as prepare_torso
        torso_projection = prepare_torso(bundle, request)
    files, evidence, geometry = build_candidate(store.read(request['character_sha256']), motion,
        bvh, bundle.kimodo_map if kimodo else bundle.bvh_map, kimodo=kimodo,
        contact_correction=request.get('contact_correction', True),
        inferred_contact_profile=inferred_profile,
        depth_review_profile=request.get('depth_review_profile'),
        on_stage=lambda stage: progress(folder, stage),
        oblique=oblique,
        torso_projection=torso_projection,
        pose_fit=pose_fit,
        moving_ankles=moving_ankles,
        clip_bounds=clip_bounds,
        character_digest=request['character_sha256'], motion_digest=motion_id['bundle_sha256'])
    progress(folder, 'publish_candidate')
    digest = store.publish(files)
    runtime = capture(SimpleNamespace(workspace_root=workspace), store, digest, folder,
                      progress=lambda stage: progress(folder, stage), cancel_requested=lambda: False,
                      storage_reference=storage_reference == PROFILE)
    local_depth=None
    if request.get('local_depth_profile'):
        from ..targets.character43.local_depth_analysis import PROFILE as LOCAL_PROFILE,analyze
        from .motion_local_depth_evidence import publish
        if request['local_depth_profile']!=LOCAL_PROFILE:raise ValueError('motion_local_depth_profile_unsupported')
        progress(folder,'local_depth')
        try:
            report=analyze(files,digest,bundle,request,triangle_traces=True,on_pair=lambda:progress(folder,'local_depth'))
        except ValueError as exc:
            report=dict(profile=LOCAL_PROFILE,job_id=request['job_id'],artifact_sha256=digest,
                authority='none',selected=False,records=[],interpolation='not_evaluated',
                failure=str(exc),scope='supplemental_check_failed_not_acceptance')
        local_depth=publish(state_root,folder,request,digest,report)
    result = dict(artifact_sha256=digest, character_animation_status=evidence['status'], runtime=runtime,
                  animations=[ANIMATION], issues=evidence['issues'],
                  geometry_passed=geometry['passed'], contact_status=evidence['contact_status'],
                  clip=request.get('clip'),
                  projection=request.get('projection'),
                  runtime_reference_profile=storage_reference or 'legacy_ideal_reference',
                  inferred_contact_profile=inferred_profile,
                  depth_order_status=evidence['depth_order_status'], authority='none', production_authorized=False)
    if request.get('torso_projection_profile') is not None:
        result['torso_projection_profile'] = request['torso_projection_profile']
    if pose_fit is not None:
        result['pose_profile'] = request['pose_profile']
    if moving_ankles is not None:
        result['moving_ankle_profile'] = request['moving_ankle_profile']
    if local_depth:result['local_depth_evidence_sha256']=local_depth
    (folder / 'worker-result.json').write_bytes(canonical_bytes(result))


if __name__ == '__main__':
    try:
        execute(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except Exception as exc:
        print(json.dumps(dict(reason_code=str(exc)[:200])))
        sys.exit(1)
