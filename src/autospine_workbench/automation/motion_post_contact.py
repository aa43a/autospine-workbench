"""Versioned post-contact candidate repair, before final depth and Runtime checks."""
from copy import deepcopy
from hashlib import sha256
from .storage_io import canonical_bytes

PROFILE = 'source-pose-post-contact-margin-v1'


def apply(document, name, motion, setup, evidence, contact, times, pose, on_stage=None):
    if pose.get('post_contact_profile') != PROFILE:
        raise ValueError('motion_post_contact_profile_unsupported')
    from ..targets.character43.support_proposal_replay import prepared_contact, without_generated_deform
    from ..targets.character43.foot_orientation_fit import fit
    from ..targets.character43.projected_area_adaptive import build
    from ..targets.character43.motion_contacts import analyze
    from .motion_target_pose import final_times
    before = deepcopy(contact)
    attempt = contact.get('phase_attempt', {})
    replay = not contact.get('selected') and attempt.get('status') == 'candidate'
    candidate = prepared_contact(document, name, contact) if contact.get('selected') or replay else deepcopy(document)
    bare = without_generated_deform(candidate, name, evidence['area_repair'])
    bare, foot = fit(bare, name, pose['foot_observations'])
    if on_stage: on_stage('post_contact_repair')
    repaired, correction = build(bare, name, setup, temporal=True, terminal_collar=True,
        proximal_ring=True, preserve_area=True, repair_band=True, fixed_band=True,
        interpolation_margin=True,
        progress=(lambda row: on_stage('post_contact_repair')) if on_stage else None)
    if repaired['animations'][name]['bones'] != bare['animations'][name]['bones']:
        raise ValueError('post_contact_repair_changed_bones')
    checked_times = final_times(repaired, name, times)
    measured = deepcopy(motion)
    inferred = 'hypothesis' in contact
    if inferred:
        hypothesis = contact['hypothesis']
        if hypothesis['ticks_per_second'] != motion['ticks_per_second']:
            raise ValueError('post_contact_tick_rate_mismatch')
        measured['markers'] = deepcopy(hypothesis['markers'])
    checked = analyze(repaired, name, measured, checked_times, evidence['reference_length_px'])
    report = deepcopy(contact)
    status = ('inferred_proxy_corrected' if inferred else 'ankle_proxy_corrected') if checked['passed'] is True else (
        'inferred_proxy_drift' if inferred else 'needs_changes') if checked['passed'] is False else checked['status']
    report.update(status=status, after=checked, selected=bool(contact.get('selected') or replay),
        output_skeleton_sha256=sha256(canonical_bytes(repaired)).hexdigest(),
        post_contact_profile=PROFILE, post_contact_before=before,
        phase_checked_times=checked_times,
        scope='sampled_ankle_proxy_not_sole_or_visual_acceptance')
    failures = correction['refinement'][-1]['check']['failures']
    evidence['post_contact_repair'] = dict(profile=PROFILE, authority='none',
        input_skeleton_sha256=sha256(canonical_bytes(document)).hexdigest(),
        contact_input_mode='replayed_proposal' if replay else 'preserved',
        foot_orientation=foot, observations=pose['foot_observations'],
        correction=correction, sampled_constraint_failures=len(failures))
    issues = [dict(stage='repair', reason_code='motion_post_contact_constraints_failed')] if failures else []
    return repaired, report, checked_times, issues
