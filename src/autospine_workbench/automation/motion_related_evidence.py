"""Verify related experimental assets without replacing jobs or inheriting decisions."""
from hashlib import sha256
import json
from ..resolved_project import canonical_sha256
from ..targets.character43.numeric_reference import read as reference


def bundle_digest(files):
    return canonical_sha256({name:sha256(raw).hexdigest() for name,raw in files.items()})


def inspect(request, character_files, candidate_files, receipt, runtime, visual=None):
    character=bundle_digest(character_files);candidate=bundle_digest(candidate_files)
    if character!=request.get('character_sha256') or candidate!=receipt.get('candidate_bundle_sha256'):
        raise ValueError('motion_related_bundle_identity')
    if not request.get('motion_identity') or receipt.get('source_identity')!=request['motion_identity']:
        raise ValueError('motion_related_motion_identity')
    before=json.loads(character_files['character-manifest.json'])
    after=json.loads(candidate_files['character-manifest.json'])
    required={'resolved_project_sha256','input_identity_sha256','skeleton_candidate_sha256',
              'layer_bindings_sha256','layer_binding_draft_sha256'}
    addresses=before.get('source_addresses',{})
    if (not required<=addresses.keys() or any(not addresses[k] for k in required)
            or after.get('source_addresses')!=addresses
            or not before.get('source_character_sha256')
            or after.get('source_character_sha256') not in (character, before['source_character_sha256'])):
        raise ValueError('motion_related_character_sources')
    if receipt.get('authority')!='none' or receipt.get('selected') is not False or receipt.get('production_authorized') is not False:
        raise ValueError('motion_related_authority')
    skeleton=sha256(candidate_files['skeleton.json']).hexdigest();ref=reference(candidate_files)
    if ref.get('skeleton_sha256')!=skeleton:raise ValueError('motion_related_reference_identity')
    expected=[(name,i,f['time']) for name,frames in ref['animations'].items() for i,f in enumerate(frames)]
    actual=[(r.get('animation'),r.get('index'),r.get('time')) for r in runtime.get('results',[])]
    if (not expected or actual!=expected or runtime.get('bundle_sha256')!=candidate
            or len(expected)!=receipt.get('sampled_frames')):
        raise ValueError('motion_related_runtime_samples')
    if (runtime.get('authority')!='none' or runtime.get('production_authorized') is not False
            or runtime.get('passed') is not True or not runtime.get('runtime_sha256')):
        raise ValueError('motion_related_runtime_evidence')
    if visual is not None:
        if (visual.get('artifact_sha256')!=candidate
                or visual.get('source_motion_ir_sha256')!=request['motion_identity'].get('motion_ir_sha256')
                or visual.get('technical_override') is not False
                or visual.get('production_authorized') is not False
                or visual.get('applies_to_other_candidates') is not False):
            raise ValueError('motion_related_visual_identity')
    result=dict(schema='autospine.motion-related-evidence/v1',
        relationship='same_motion_and_character_source_records_not_same_candidate_or_strategy',
        request_sha256=canonical_sha256(request),character_sha256=character,
        candidate_sha256=candidate,skeleton_sha256=skeleton,
        character_sources_sha256=canonical_sha256(addresses),
        receipt_sha256=canonical_sha256(receipt),runtime_report_sha256=canonical_sha256(runtime),
        runtime_version=runtime.get('runtime_version'),target_version=after.get('target'),
        sampled_frames=len(expected),visual_evidence_sha256=canonical_sha256(visual) if visual else None,
        visual=visual,authority='none',selected=False,production_authorized=False,
        limitations=['not_a_parent_chain_proof','no_new_runtime_capture',
                    'no_inherited_baseline_acceptance','no_job_replacement'])
    if 'contact_audit' in receipt:
        if set(ref['animations'])!={'external-motion'}:
            raise ValueError('motion_related_contact_animations')
        from .motion_related_contact import summary
        result['additional_checks']=summary(receipt['contact_audit'],candidate,skeleton,runtime,
                                            [f['time'] for f in ref['animations']['external-motion']])
    return result
