"""Recompute final joint intent from a verified source, with explicit camera/clip."""
from hashlib import sha256
from copy import deepcopy
import json

from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..resolved_project import canonical_sha256
from ..targets.character43.knee_source_samples import read as source_samples
from ..targets.character43.motion_clip import boundaries, clip_motion
from ..targets.character43.oblique_target import prepare
from ..targets.character43.source_pose_fidelity import inspect
from .storage_io import canonical_bytes


def measure(files, candidate, bundle, request):
    # Correctives may omit MotionIR. Reconstruct it from verified bytes and the
    # recorded view/clip, never from a different baseline's projection report.
    inputs = dict(files)
    motion = bundle.motion
    if request.get('projection') is not None:
        motion, _ = prepare(bundle, request['projection'])
    ticks = next(t for t in motion['tracks'] if t['property'] == 'rotation')['keys']
    motion = clip_motion(motion, boundaries(request.get('clip'), [k['tick'] for k in ticks]))
    inputs.setdefault('motion-ir.json', canonical_bytes(motion))
    name, vectors, times, source_times = source_samples(inputs, bundle, request)
    yaw = (request.get('projection') or {}).get('yaw_degrees', 0)
    result = inspect(json.loads(files['skeleton.json']), name, vectors, times, yaw)
    lookup = dict(zip(times, source_times))
    for row in result['rows']:
        row['source_time'] = lookup[row['time']]
    result.update(profile='related-final-source-pose-v1', artifact_sha256=candidate,
        skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), animation=name,
        source_request=request, source_request_sha256=canonical_sha256(request),
        samples=len(times), times=times, source_times=source_times,
        animation_modified=False, production_authorized=False,
        interpolated_frames_checked=False)
    return result


def _matches_saved_audit(audit, expected):
    if canonical_sha256(audit) == canonical_sha256(expected):
        return True
    # Older v1 receipts predate these two additive knee diagnostics. Reproduce
    # their exact shape, not arbitrary missing fields or changed measurements.
    fields = ('hidden_bend_degrees', 'projected_bend_degrees')
    knees = [row['knee'][side] for row in audit.get('rows', []) if 'knee' in row
             for side in ('source', 'target')]
    if not knees or any(key in knee for knee in knees for key in fields):
        return False
    legacy = deepcopy(expected)
    for row in legacy.get('rows', []):
        if 'knee' in row:
            for side in ('source', 'target'):
                for key in fields:
                    row['knee'][side].pop(key, None)
    return canonical_sha256(audit) == canonical_sha256(legacy)


def verify(files, receipt, state_root):
    """Publication and reads reproduce every measurement, not just a supplied flag."""
    if 'pose_audit' not in receipt:
        return
    audit = receipt['pose_audit']; request = audit['source_request']
    identity = request['motion_identity']
    if (identity != receipt.get('source_identity')
            or canonical_sha256(request) != receipt.get('source_request_sha256')):
        raise ValueError('motion_related_pose_source_identity')
    bundle = VerifiedMotionBundleReader(state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    expected = measure(files, receipt['candidate_bundle_sha256'], bundle, request)
    if not _matches_saved_audit(audit, expected):
        raise ValueError('motion_related_pose_measurement_changed')


def summary(audit, candidate, skeleton, identity, source_request_sha):
    request = audit.get('source_request', {})
    if (audit.get('profile') != 'related-final-source-pose-v1'
            or audit.get('artifact_sha256') != candidate or audit.get('skeleton_sha256') != skeleton
            or request.get('motion_identity') != identity
            or audit.get('source_request_sha256') != source_request_sha
            or canonical_sha256(request) != source_request_sha):
        raise ValueError('motion_related_pose_identity')
    if (audit.get('authority') != 'none' or audit.get('selected') is not False
            or audit.get('animation_modified') is not False
            or audit.get('production_authorized') is not False
            or audit.get('interpolated_frames_checked') is not False):
        raise ValueError('motion_related_pose_scope')
    limbs = []; events = []
    for limb in ('arm', 'leg'):
        for side in ('left', 'right'):
            rows = [r for r in audit['rows'] if (r['limb'], r['side']) == (limb, side)]
            if [r['time'] for r in rows] != audit['times'] or not rows:
                raise ValueError('motion_related_pose_samples')
            angles = [v for r in rows for v in r['direction_error_degrees'] if v is not None]
            worst = max(rows, key=lambda r: r['endpoint_error_ratio'])
            limbs.append(dict(limb=limb, side=side, samples=len(rows),
                max_direction_error_degrees=max(angles) if angles else None,
                max_endpoint_error_ratio=worst['endpoint_error_ratio'],
                worst_time=worst['time'], source_time=worst['source_time']))
            for r in rows:
                status = r.get('knee', {}).get('status')
                if status not in (None, 'projected_side_consistent', 'source_nearly_straight'):
                    events.append(dict(time=r['time'], source_time=r['source_time'], side=side,
                        reason=status, source_bend=r['knee']['source'].get('screen_bend_ratio'),
                        target_bend=r['knee']['target'].get('screen_bend_ratio')))
    return dict(audit_sha256=canonical_sha256(audit), samples=audit['samples'],
        yaw_degrees=audit['yaw'], clip=request.get('clip'), limbs=limbs, events=events,
        status='requires_review', scope=audit['scope'], interpolated_frames_checked=False,
        limitations=['bone_axes_not_mesh_outline', 'camera_side_not_anatomical_forward',
                     'no_depth_occlusion_or_visual_admission'])
