"""Profile-specific evidence gate; legacy review identities remain unchanged."""
from hashlib import sha256
import json
from .regional_depth_contract import PROFILE as TRANSFORM_PROFILE


def measured_details(regional):
    """Reconcile the aggregate with the producer's independent sub-reports."""
    refinement = regional.get('refinement')
    if not isinstance(refinement, dict) or not isinstance(refinement.get('rows'), list):
        return False
    for row in refinement['rows']:
        if not isinstance(row, dict) or not isinstance(row.get('checks'), list):
            return False
        for check in row['checks']:
            if not isinstance(check, dict) or check.get('status') not in (
                    'no_overlap', 'uniform_front_proxy', 'uniform_back_proxy',
                    'requires_partition_or_more_depth'):
                return False
    for name in ('cloth_constraints', 'limb_constraints'):
        detail = regional.get(name)
        if detail is None:  # A producer may have no applicable cloth/leg pairs.
            continue
        if not isinstance(detail, dict):
            return False
        count = detail.get('unmeasured_samples')
        if type(count) is not int or count != 0:
            return False
    return True


def evaluate(files, depth):
    regional = depth.get('regional', {})
    order = depth.get('order', {})
    if order.get('failures'):
        return 'needs_changes'
    count = regional.get('unmeasured_samples')
    if type(count) is not int or count != 0:
        return 'unmeasured'
    if not measured_details(regional):
        return 'unmeasured'
    if not regional.get('refinement') or order != regional.get('order'):
        return 'unmeasured'
    if depth.get('selected') is not True or order.get('status') not in ('candidate', 'no_visible_order_change'):
        return 'unmeasured'
    transform = json.loads(files.get('motion-regional-transform.json', b'{}'))
    if (transform.get('profile') != TRANSFORM_PROFILE or
            transform.get('candidate_skeleton_sha256') != sha256(files['skeleton.json']).hexdigest()):
        return 'unmeasured'
    return 'sampled_pass'
