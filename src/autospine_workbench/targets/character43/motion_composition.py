"""Merge a source-bound motion candidate without replacing the character or existing clips."""
from hashlib import sha256
import json
from ...automation.storage_io import canonical_bytes
from ...manifest_artifacts import require_sha256
from .deformation_qa import inspect


def compose(base, motion, base_digest, motion_digest):
    require_sha256(base_digest, 'Character source'); require_sha256(motion_digest, 'Motion candidate')
    manifest = json.loads(base['character-manifest.json'])
    incoming = json.loads(motion['character-manifest.json'])
    if incoming.get('source_character_sha256') != base_digest or incoming.get('authority') != 'none' \
            or incoming.get('production_authorized') is not False:
        raise ValueError('character_motion_composition_source')
    original = json.loads(base['skeleton.json']); added = json.loads(motion['skeleton.json'])
    if {k: v for k, v in original.items() if k != 'animations'} != {k: v for k, v in added.items() if k != 'animations'}:
        raise ValueError('character_motion_composition_rig_changed')
    textures = {n: raw for n, raw in base.items() if n.endswith('.png') or n == 'skeleton.atlas'}
    if textures != {n: raw for n, raw in motion.items() if n.endswith('.png') or n == 'skeleton.atlas'}:
        raise ValueError('character_motion_composition_texture_changed')
    if not added['animations'] or set(original['animations']) & set(added['animations']):
        raise ValueError('character_motion_composition_duplicate')
    for source in (base, motion):
        if not inspect(source)['passed']:
            raise ValueError('character_motion_composition_geometry')
    reference = json.loads(base['numeric-reference.json'])
    added_reference = json.loads(motion['numeric-reference.json'])
    original['animations'].update(added['animations'])
    result = dict(base); result['skeleton.json'] = canonical_bytes(original)
    if 'editor/skeleton.json' in base:
        editor = json.loads(base['editor/skeleton.json'])
        if editor.get('animations') != json.loads(base['skeleton.json'])['animations']:
            raise ValueError('character_motion_composition_editor_changed')
        editor['animations'].update(added['animations']); result['editor/skeleton.json'] = canonical_bytes(editor)
    reference['animations'].update(added_reference['animations'])
    reference['skeleton_sha256'] = sha256(result['skeleton.json']).hexdigest()
    result['numeric-reference.json'] = canonical_bytes(reference)
    result['deformation.json'] = canonical_bytes(inspect(result))
    for name in ('motion-review.json', 'motion-ir.json', 'root-correction.json'):
        if name in motion: result['motion-candidates/'+motion_digest+'/'+name] = motion[name]
    manifest.update(profile='exact-character-motion-composition-v1', animations=sorted(original['animations']),
                    status='needs_review', authority='none', production_authorized=False, full_character_animation=False,
                    qa=dict(runtime_status='not_run', full_character_contact_status='not_evaluated'))
    manifest.setdefault('motion_compositions', []).append(dict(source_character_sha256=base_digest,
        motion_candidate_sha256=motion_digest, animations=sorted(added['animations']), status='candidate'))
    manifest['files'] = {n: sha256(raw).hexdigest() for n, raw in result.items() if n != 'character-manifest.json'}
    result['character-manifest.json'] = canonical_bytes(manifest)
    return result
