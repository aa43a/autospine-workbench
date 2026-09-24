"""Switch a single slot to a pose-specific mesh without alpha overlays.

The variant may change topology, UV and deform, but not skeleton, source slot
order or any other attachment. Abrupt visual transitions remain review issues.
"""
from copy import deepcopy
import math
import struct

from ...resolved_project import canonical_sha256


def compile_variant(document, variant, *, slot, animation, interval, source_sha256):
    if canonical_sha256(document) != source_sha256:
        raise ValueError('pose_variant_source_changed')
    if (len(document['skins']) != 1 or len(variant['skins']) != 1 or
            document['skins'][0].get('name', 'default') != 'default'):
        raise ValueError('pose_variant_default_skin_required')
    def mesh(doc):
        return doc['skins'][0]['attachments'][slot][slot]
    if any(mesh(d).get('type') != 'mesh' or mesh(d).get('parent') for d in (document, variant)):
        raise ValueError('pose_variant_mesh_required')
    def strip(doc):
        result = deepcopy(doc)
        result['skins'][0]['attachments'][slot][slot] = {}
        for motion_name, motion in result['animations'].items():
            if motion.get('deform'):
                raise ValueError('pose_variant_legacy_deform_unsupported')
            if motion.get('slots', {}).get(slot, {}).get('attachment'):
                raise ValueError('pose_variant_existing_attachment_timeline')
            if motion_name == animation:
                channels = motion.setdefault('attachments', {}).setdefault('default', {}).setdefault(slot, {}).setdefault(slot, {})
                channels.pop('deform', None)
        return result
    if strip(document) != strip(variant):
        raise ValueError('pose_variant_changes_outside_mesh_and_deform')
    def times(value):
        if isinstance(value, dict):
            return [v for k, v in value.items() if k == 'time'] + [
                t for k, v in value.items() if k != 'time' for t in times(v)]
        if isinstance(value, list):
            return [t for child in value for t in times(child)]
        return []
    duration = max(times(document['animations'][animation]), default=0)
    if (not isinstance(interval, list) or len(interval) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in interval) or
            not 0 <= interval[0] < interval[1] <= duration):
        raise ValueError('pose_variant_interval_invalid')
    effective = [struct.unpack('f', struct.pack('f', t))[0] for t in interval]
    if effective[0] >= effective[1]:
        raise ValueError('pose_variant_interval_collapsed')
    source_slot = next(s for s in document['slots'] if s['name'] == slot)
    if source_slot.get('attachment') != slot:
        raise ValueError('pose_variant_setup_attachment_mismatch')
    name = slot + '-pose-' + canonical_sha256(variant)[:16]
    result = deepcopy(document)
    choices = result['skins'][0]['attachments'][slot]
    if name in choices:
        raise ValueError('pose_variant_attachment_exists')
    choices[name] = deepcopy(mesh(variant))
    choices[name].setdefault('path', mesh(document).get('path', slot))
    keys = variant['animations'][animation].get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform')
    motion = result['animations'][animation]
    if keys:
        motion.setdefault('attachments', {}).setdefault('default', {}).setdefault(slot, {})[name] = dict(deform=deepcopy(keys))
    timeline = [] if interval[0] == 0 else [dict(time=0, name=slot)]
    timeline.extend([dict(time=interval[0], name=name), dict(time=interval[1], name=slot)])
    motion.setdefault('slots', {}).setdefault(slot, {})['attachment'] = timeline
    return result, dict(profile='pose-specific-attachment-variant-v1', animation=animation,
        slot=slot, original_attachment=slot, variant_attachment=name, interval=interval,
        runtime_interval=effective, source_sha256=source_sha256,
        variant_sha256=canonical_sha256(variant), output_sha256=canonical_sha256(result),
        authority='none', selected=False, visual_status='not_evaluated',
        limitations=['hard_switch_requires_boundary_continuity_validation',
                     'new_topology_uv_and_deform_require_runtime_validation'])
