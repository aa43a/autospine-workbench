"""Build a candidate from explicitly reviewed points, preserving central anchors."""
from copy import deepcopy
import math
import re

from ...benchmark.joint_draft import JOINTS, validate_joint_draft
from ...resolved_project import canonical_sha256
from .skeleton import _extend, _point

SCHEMA = "autospine.assisted-skeleton-candidate/v1"


def _require(condition):
    if not condition:
        raise ValueError("assisted_skeleton_input_invalid")


def _plan(p):
    pelvis, chest, neck, head = [p[key] for key in ('pelvis', 'chest', 'neck', 'head')]
    torso = math.dist(pelvis, chest)
    if torso < 2:
        raise ValueError('assisted_skeleton_torso_too_short')
    if not head[1] < neck[1] < chest[1] < pelvis[1] < p['root'][1]:
        raise ValueError('assisted_skeleton_vertical_order_invalid')
    spine = [(a+b)/2 for a, b in zip(pelvis, chest)]
    plan = [('root', None, p['root'], pelvis, 'assisted_review', ['root', 'pelvis'], 'reviewed_root_pelvis'),
            ('pelvis', 'root', pelvis, spine, 'derived', ['pelvis', 'chest'], 'reviewed_torso_midpoint'),
            ('spine', 'pelvis', spine, chest, 'derived', ['pelvis', 'chest'], 'reviewed_torso_midpoint'),
            ('chest', 'spine', chest, neck, 'assisted_review', ['chest', 'neck'], 'reviewed_central_points'),
            ('neck', 'chest', neck, head, 'assisted_review', ['neck', 'head'], 'reviewed_central_points'),
            ('head', 'neck', head, _extend(neck, head, .15*torso), 'fallback', ['neck', 'head'], 'head_tip_extension')]
    for side, suffix in (('left', 'l'), ('right', 'r')):
        shoulder, elbow, wrist, hip, knee, ankle = [f'{name}.{side}' for name in ('shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle')]
        plan.extend([
            (f'clavicle_{suffix}', 'chest', chest, p[shoulder], 'assisted_review', ['chest', shoulder], 'reviewed_clavicle'),
            (f'upperarm_{suffix}', f'clavicle_{suffix}', p[shoulder], p[elbow], 'assisted_review', [shoulder, elbow], 'reviewed_limb'),
            (f'forearm_{suffix}', f'upperarm_{suffix}', p[elbow], p[wrist], 'assisted_review', [elbow, wrist], 'reviewed_limb'),
            (f'hand_{suffix}', f'forearm_{suffix}', p[wrist], _extend(p[elbow], p[wrist], .05*torso), 'fallback', [elbow, wrist], 'hand_tip_extension'),
            (f'thigh_{suffix}', 'pelvis', p[hip], p[knee], 'assisted_review', [hip, knee], 'reviewed_limb'),
            (f'calf_{suffix}', f'thigh_{suffix}', p[knee], p[ankle], 'assisted_review', [knee, ankle], 'reviewed_limb'),
            (f'foot_{suffix}', f'calf_{suffix}', p[ankle], _extend(p[knee], p[ankle], .05*torso), 'fallback', [knee, ankle], 'foot_tip_extension'),
        ])
    return plan


def _compile(points, canvas):
    bones, frames = [], {}
    for identifier, parent, head, tail, kind, sources, reason in _plan(points):
        head, tail = _point(head, canvas), _point(tail, canvas)
        length = math.dist(head, tail)
        if length < 1:
            raise ValueError('assisted_skeleton_bone_too_short')
        angle = math.degrees(math.atan2(tail[1]-head[1], tail[0]-head[0]))
        parent_head, parent_angle = frames[parent] if parent is not None else ([0., 0.], 0.)
        r = math.radians(-parent_angle)
        dx, dy = head[0]-parent_head[0], head[1]-parent_head[1]
        local = {'x': dx*math.cos(r)-dy*math.sin(r), 'y': dx*math.sin(r)+dy*math.cos(r),
                 'rotation_degrees': angle-parent_angle}
        bones.append({'id': identifier, 'parent_id': parent, 'head_xy': head, 'tail_xy': tail,
                      'length': length, 'world_rotation_degrees': angle, 'setup_local': local,
                      'provenance': {'kind': kind, 'source_joint_ids': sources, 'reason_codes': [reason]}})
        frames[identifier] = (head, angle)
    return bones


def build_reviewed_skeleton(candidate, assisted):
    """Caller replays the assisted source closure; this never produces a pose IR."""
    _require(type(candidate) is dict and type(candidate.get('canvas')) is list
             and len(candidate['canvas']) == 2
             and all(type(v) is int and 0 < v <= 4096 for v in candidate['canvas']))
    keys = {'schema', 'authority', 'annotation_mode', 'independent_annotation', 'candidate_sha256',
            'source_pose_sha256', 'source_baseline_sha256', 'reviewed_joint_ids', 'draft'}
    _require(type(assisted) is dict and set(assisted) == keys
             and assisted['schema'] == 'autospine.benchmark-assisted-joint-draft/v1'
             and assisted['authority'] == 'none' and assisted['annotation_mode'] == 'model_assisted'
             and assisted['independent_annotation'] is False
             and assisted['candidate_sha256'] == canonical_sha256(candidate))
    for key in ('source_pose_sha256', 'source_baseline_sha256'):
        _require(type(assisted[key]) is str and re.fullmatch('[0-9a-f]{64}', assisted[key]) is not None)
    draft = validate_joint_draft(candidate, assisted['draft'])
    canvas = candidate['canvas']
    reviewed = assisted['reviewed_joint_ids']
    _require(type(reviewed) is list and all(type(j) is str and j in JOINTS for j in reviewed)
             and len(reviewed) == len(set(reviewed)))
    report = {'schema': SCHEMA, 'authority': 'none', 'diagnostic_only': True, 'production_authorized': False,
              'candidate_sha256': canonical_sha256(candidate), 'source_assisted_sha256': canonical_sha256(assisted),
              'profile': 'assisted-canonical-v1', 'status': 'blocked', 'reason_codes': [],
              'canvas': deepcopy(canvas), 'coordinate_system': 'psd_canvas', 'bones': []}
    if set(reviewed) != set(JOINTS):
        report['reason_codes'] = ['all_joint_reviews_required']
        return report
    if any(row['status'] != 'observed' for row in draft['records']):
        report['reason_codes'] = ['all_joint_positions_required']
        return report
    points = {row['joint_id']: row['position'] for row in draft['records']}
    try:
        report['bones'] = _compile(points, canvas)
    except ValueError as exc:
        reason = str(exc)
        report['reason_codes'] = [reason if reason.startswith('assisted_skeleton_') else
                                  'assisted_skeleton_geometry_invalid']
        return report
    report.update(status='candidate_requires_review', reason_codes=['reviewed_central_points_preserved',
                  'terminal_points_fallback', 'skeleton_review_required'])
    return report


def validate_reviewed_skeleton(candidate, assisted, document):
    expected = build_reviewed_skeleton(candidate, assisted)
    if type(document) is not dict or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError('assisted_skeleton_mismatch')
    return deepcopy(expected)
