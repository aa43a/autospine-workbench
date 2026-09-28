"""Describe a verified related source without borrowing baseline pass flags."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from ..resolved_project import canonical_sha256


def review(resolved):
    files = resolved['files']
    if 'motion-review.json' in files:
        return json.loads(files['motion-review.json'])
    related = resolved.get('related')
    if not related or related['candidate_sha256'] != resolved['artifact_sha256']:
        raise ValueError('joint_animation_related_evidence_required')
    document = json.loads(files['skeleton.json'])
    bones = {b['name']: b for b in document['bones']}
    length = sum(math.hypot(bones[n]['x'], bones[n]['y'])
                 for n in ('calf_l', 'foot_l', 'calf_r', 'foot_r'))/2
    if not math.isfinite(length) or length <= 0:
        raise ValueError('joint_animation_reference_length_invalid')
    # These registrations predate the main review contract. Preserve their
    # exact diagnostic evidence; absence of a stage is not a successful stage.
    return dict(schema='autospine.joint-related-source-review/v1',
        source_skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        reference_length_px=length, related_evidence=deepcopy(related['evidence']),
        related_receipt_sha256=canonical_sha256(related['receipt']),
        issues=[dict(stage='inherited', reason_code='related_body_stage_evidence_requires_review')],
        inherited_scope='verified_related_candidate_not_baseline_checks_or_acceptance',
        source_pose_fit={}, geometry_passed=None, depth_order_status='unmeasured',
        runtime_status='source_evidence_only', authority='none', selected=False,
        production_authorized=False)
