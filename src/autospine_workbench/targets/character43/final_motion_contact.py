"""Recheck contact on the final rendered timeline without altering the motion."""
from copy import deepcopy
from hashlib import sha256
import json
import math
from ...resolved_project import canonical_sha256
from .motion_contacts import analyze
from .contact_windows import for_motion


def recheck(document, name, motion, contact, times, reference_length):
    duration = motion['duration_ticks'] / motion['ticks_per_second']
    if (not 2 <= len(times) <= 4097 or times[0] != 0 or times[-1] != duration
            or any(not math.isfinite(t) or t < 0 or t > duration for t in times)
            or any(b <= a for a,b in zip(times,times[1:]))):
        raise ValueError('motion_final_contact_times_invalid')
    source = deepcopy(motion)
    inferred = 'hypothesis' in contact
    if inferred:
        hypothesis = contact['hypothesis']
        if hypothesis['markers'] and hypothesis['ticks_per_second'] != motion['ticks_per_second']:
            raise ValueError('motion_final_contact_tick_rate_mismatch')
        source['markers'] = for_motion(motion, hypothesis, contact.get('clip_bounds'))
    checked = analyze(document, name, source, times, reference_length)
    report = deepcopy(contact)
    report['pre_final_after'] = report.get('after')
    report['after'] = checked
    if checked['passed'] is None:
        report['status'] = checked['status']
    elif checked['passed']:
        prefix = 'inferred_proxy_' if inferred else 'ankle_proxy_'
        report['status'] = prefix + ('corrected' if contact.get('selected') else 'passed')
    else:
        report['status'] = 'inferred_proxy_drift' if inferred else 'needs_changes'
    report['final_timeline_check'] = dict(profile='final-timeline-ankle-proxy-v1',
        skeleton_sha256=canonical_sha256(document), animation=name,
        times_sha256=canonical_sha256(times), samples=len(times),
        authority='none', scope='final_cpu_bone_samples_not_gpu_sole_or_continuous_contact')
    return report


def for_candidate(files, artifact, runtime):
    from .numeric_reference import read
    if runtime.get('bundle_sha256') != artifact:
        raise ValueError('motion_final_contact_runtime_mismatch')
    reference = read(files)
    digest = sha256(files['skeleton.json']).hexdigest()
    if reference['skeleton_sha256'] != digest:
        raise ValueError('motion_final_contact_reference_mismatch')
    if set(reference['animations']) != {'external-motion'}:
        raise ValueError('motion_final_contact_animation_mismatch')
    times = [r['time'] for r in reference['animations']['external-motion']]
    if (any(r['animation'] != 'external-motion' for r in runtime['results']) or
            [r['time'] for r in runtime['results']] != times):
        raise ValueError('motion_final_contact_runtime_times_mismatch')
    result = recheck(json.loads(files['skeleton.json']), 'external-motion',
        json.loads(files['motion-ir.json']), json.loads(files['motion-contact.json']), times,
        json.loads(files['motion-review.json'])['reference_length_px'])
    result['artifact_sha256'] = artifact
    result['runtime_numeric_passed'] = runtime.get('passed')
    result['authority'] = 'none'
    return result
