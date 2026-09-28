"""Candidate-bound source camera diagnostics over the exact retained clip."""
from ...resolved_project import canonical_sha256
from .knee_source_samples import read
from .lower_limb_projection import view_summary
from .source_view_scan import scan
from .oblique_motion import project
from .torso_projection_source import anchors, reference_shapes


def build(files, artifact, bundle, request):
    animation, vectors, times, source_times = read(files, bundle, request)
    from .camera_track import PROFILE as CAMERA_PROFILE
    if (request.get('projection') or {}).get('profile')==CAMERA_PROFILE:
        return dict(profile='candidate-source-view-tradeoffs-v1',artifact_sha256=artifact,status='unavailable',
            reason='continuous_camera_has_no_single_current_yaw',authority='none',selected=False,
            production_authorized=False,camera_keys=request['projection']['keys'])
    front, ticks = anchors(bundle, 0)
    by_time = dict(zip([t / 1e6 for t in ticks], front))
    if len(front) != len(ticks) or len(by_time) != len(ticks) or any(t not in by_time for t in source_times):
        raise ValueError('view_tradeoff_source_times_mismatch')
    current = (request.get('projection') or {}).get('yaw_degrees', 0)
    yaws = sorted(set([*range(-90, 91, 15), current]))
    candidates = scan(vectors, yaws)
    for candidate in candidates:
        yaw = candidate['yaw_degrees']
        candidate['current'] = yaw == current
        knee = view_summary(vectors, yaw)
        if knee['worst'] is not None:
            index = knee['worst']['frame']
            knee['worst'].update(time=times[index], source_time=source_times[index])
        candidate['knees'] = knee
        frames = [[project(p, yaw) for p in by_time[t]] for t in source_times]
        try:
            torso = reference_shapes(frames, times, front[0])
            rows = torso['records']
            candidate['torso'] = dict(status='measured', source_supported=all(not r['reasons'] for r in rows),
                reasons=sorted({reason for r in rows for reason in r['reasons']}), limits=torso['limits'])
        except ValueError as exc:
            # A degenerate torso reference is missing evidence, not a good camera.
            if str(exc) not in ('torso_anchor_axis_degenerate', 'torso_initial_view_degenerate'):
                raise
            candidate['torso'] = dict(status='unmeasured', source_supported=None, reasons=[str(exc)])
    report = dict(profile='candidate-source-view-tradeoffs-v1', artifact_sha256=artifact,
        animation=animation, motion_identity=request['motion_identity'], request_sha256=canonical_sha256(request),
        vectors_sha256=canonical_sha256(vectors), source_samples=len(times), times=times, source_times=source_times,
        current_yaw=current, clip=request.get('clip'), candidates=candidates, authority='none', selected=False,
        production_authorized=False, scope='source_clip_samples_not_character_camera_admission',
        limitations=['frontal_artwork_does_not_supply_side_or_back_surfaces',
            'target_geometry_contact_occlusion_and_visual_review_required',
            'sampled_angles_not_continuous_motion_proof', 'no_candidate_replacement'])
    report['report_sha256'] = canonical_sha256(report)
    return report
