"""Whole-character IK wave with explicit geometry admission and optional bounded repair."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from ...manifest_artifacts import require_sha256
from ...motion_builtin import build_builtin_motion
from .wave_motion import build_wave
from .affine_pose import sample
from .deformation_qa import inspect


def generate(files, source_digest, *, repair=False, drape_helpers=(), rotary_cloth=False):
    require_sha256(source_digest, 'Character source')
    if rotary_cloth and (not drape_helpers or repair):
        raise ValueError('character_wave_rotary_options')
    original = json.loads(files['skeleton.json'])
    if 'wave-left' in original['animations']:
        raise ValueError('character_wave_name_conflict')
    document, evidence = build_wave(original)
    if drape_helpers:
        from .drape_direction import apply
        document, direction = apply(document, 'wave-left', drape_helpers)
        evidence['drape_direction'] = direction
    if rotary_cloth:
        from .cloth_rotary_transition import bake
        document, transition = bake(document, 'wave-left', drape_helpers)
        evidence['cloth_rotary_transition'] = transition
    motion = build_builtin_motion('wave.left')
    duration = motion.document['duration_ticks']/motion.document['ticks_per_second']
    # Twice the repair grid also checks interpolation between baked deform keys.
    times = sorted({duration*i/512 for i in range(513)} | {
        k['time'] for tracks in document['animations']['wave-left']['bones'].values()
        for keys in tracks.values() for k in keys})

    def check(doc):
        raw = canonical_bytes(doc)
        reference = canonical_bytes(dict(skeleton_sha256=sha256(raw).hexdigest(), animations={
            'wave-left': [dict(time=t, vertices=sample(doc, 'wave-left', t)[0]) for t in times]}))
        pair = {'skeleton.json': raw, 'numeric-reference.json': reference}
        return pair, inspect(pair)

    result, qa = check(document)
    original_qa = qa
    correction = None
    if repair and not qa['passed']:
        from .affine_area_repair import repair as correct
        candidate, correction = correct(document, 'wave-left', convergent=True)
        corrected, checked = check(candidate)
        correction['selected'] = checked['passed']
        correction['verification_samples'] = len(times)
        if checked['passed']:
            result, qa = corrected, checked
        result['wave-repair-deformation.json'] = canonical_bytes(checked)
        result['wave-repair.json'] = canonical_bytes(correction)
    result.update({n: data for n, data in files.items() if n.endswith('.png') or n == 'skeleton.atlas'})
    evidence.update(profile='whole-character-ik-wave-v1', character_sha256=source_digest,
                    geometry_passed=qa['passed'], runtime_status='not_evaluated',
                    reason_code=None if qa['passed'] else 'character_wave_geometry_failed',
                    failing_slots=[r['slot'] for r in qa['records'] if not r['passed']],
                    sample_count=len(times), contact_status='not_evaluated',
                    sleeve_correctives='existing_clips_only_not_transferred_to_new_motion')
    result.update({'deformation.json': canonical_bytes(qa),
                   'wave-original-deformation.json': canonical_bytes(original_qa),
                   'motion-ir.json': motion.canonical_json.encode(),
                   'motion-review.json': canonical_bytes(evidence)})
    result['character-manifest.json'] = canonical_bytes(dict(
        schema='autospine.character-motion-preview/v1', profile='whole-character-ik-wave-v1',
        source_character_sha256=source_digest, animations=['wave-left'], authority='none',
        production_authorized=False, status='preview_only' if qa['passed'] else 'blocked',
        files={n: sha256(data).hexdigest() for n, data in result.items()}))
    return result
