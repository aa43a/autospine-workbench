"""Profile-specific evidence gate; legacy review identities remain unchanged."""
from hashlib import sha256
import json
from .regional_depth_contract import PROFILE as TRANSFORM_PROFILE


def evaluate(files, depth):
    regional = depth.get('regional', {})
    order = depth.get('order', {})
    if order.get('failures'):
        return 'needs_changes'
    count = regional.get('unmeasured_samples')
    if type(count) is not int or count != 0:
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
