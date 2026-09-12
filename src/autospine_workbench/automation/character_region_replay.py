"""Preserve an explicit exclusion when unrelated binding revisions change its container."""
from hashlib import sha256
import json
from ..resolved_project import canonical_sha256
from ..targets.character43.region_exclusion import apply

FIXED = {'resolved_project_sha256', 'benchmark_manifest_sha256', 'semantic_candidate_sha256',
         'skeleton_candidate_sha256', 'layer_bindings_sha256'}
DERIVED = {'animated_registration_sha256', 'input_identity_sha256', 'layer_binding_draft_sha256',
           'base_bundle_sha256', 'sleeve_job_sha256', 'sleeve_zip_inventory_sha256'}


def apply_current(store, files, decision):
    if sha256(files['character-manifest.json']).hexdigest() == decision['manifest_sha256']:
        return apply(files, decision)
    original = store.read(decision['source_bundle_sha256'])
    apply(original, decision)  # Prove the original reviewed scope, including its texture.
    before = json.loads(original['character-manifest.json'])
    after = json.loads(files['character-manifest.json'])
    old, new = before.get('source_addresses', {}), after.get('source_addresses', {})
    if not FIXED <= old.keys() or old.keys() != new.keys() or any(
            old[k] != new[k] for k in old if k not in DERIVED):
        raise ValueError('character_region_replay_source')
    if any(k not in old or old[k] == new[k] for k in (
            'animated_registration_sha256', 'input_identity_sha256', 'layer_binding_draft_sha256')):
        raise ValueError('character_region_replay_not_binding_update')
    region, layer = decision['region_id'], decision['layer_id']
    a = [r for r in before['layers'] if r['layer_id'] == layer]
    b = [r for r in after['layers'] if r['layer_id'] == layer]
    if len(a) != 1 or a != b:
        raise ValueError('character_region_replay_layer_changed')
    old_rig, new_rig = (json.loads(f['skeleton.json']) for f in (original, files))
    if not old_rig.get('bones') or old_rig['bones'] != new_rig.get('bones'):
        raise ValueError('character_region_replay_bones_changed')
    if [s for s in old_rig['slots'] if s['name'] == region] != [s for s in new_rig['slots'] if s['name'] == region]:
        raise ValueError('character_region_replay_slot_changed')
    if len(old_rig['skins']) != 1 or len(new_rig['skins']) != 1:
        raise ValueError('character_region_replay_skins_changed')
    attachment = old_rig['skins'][0]['attachments'][region]
    if attachment != new_rig['skins'][0]['attachments'][region]:
        raise ValueError('character_region_replay_attachment_changed')
    texture = 'images/' + attachment[region].get('path', region) + '.png'
    if original[texture] != files[texture]:
        raise ValueError('character_region_replay_texture_changed')
    current = dict(decision, source_bundle_sha256=store.publish(files),
                   manifest_sha256=sha256(files['character-manifest.json']).hexdigest(),
                   scope_replay=dict(profile='unchanged-region-binding-update-v1',
                       original_decision_sha256=canonical_sha256(decision), original_decision=decision,
                       changed_source_fields=sorted(k for k in old if old[k] != new[k]),
                       authority='none', new_human_confirmation=False))
    return apply(files, current)
