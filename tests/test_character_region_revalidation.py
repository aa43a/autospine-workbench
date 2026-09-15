from copy import deepcopy
from hashlib import sha256
import json
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.targets.character43.region_revalidation import digest, revalidate
from test_character_region_exclusion import fixture


def source():
    files, decision = fixture()
    manifest = json.loads(files['character-manifest.json'])
    manifest['source_addresses'] = {'input_identity_sha256': '1'*64, 'base_bundle_sha256': '2'*64}
    files['character-manifest.json'] = raw(manifest)
    decision.update(source_bundle_sha256=digest(files), reversible=True,
                    manifest_sha256=sha256(files['character-manifest.json']).hexdigest())
    return files, decision


class RegionRevalidationTests(unittest.TestCase):
    def test_new_build_preserves_original_decision_without_new_approval(self):
        old, decision = source(); new = dict(old)
        manifest = json.loads(new['character-manifest.json'])
        manifest['source_addresses']['base_bundle_sha256'] = '3'*64
        manifest['layers'].append(dict(layer_id='empty', state='not_visible'))
        new['character-manifest.json'] = raw(manifest)
        before = deepcopy((old, new, decision))
        result = revalidate(old, new, [decision])[0]
        self.assertEqual(result['source_bundle_sha256'], digest(new))
        self.assertEqual(result['scope_replay']['original_decision'], decision)
        self.assertFalse(result['scope_replay']['new_human_confirmation'])
        self.assertEqual((old, new, decision), before)

    def test_scope_changes_cannot_reuse_human_confirmation(self):
        for mutation in ('source', 'layer', 'image', 'geometry', 'bones', 'motion', 'approval', 'duplicate', 'draw_order'):
            with self.subTest(mutation=mutation):
                old, decision = source(); new = dict(old); decisions = [decision]
                if mutation in ('source', 'layer'):
                    manifest = json.loads(new['character-manifest.json'])
                    if mutation == 'source': manifest['source_addresses']['input_identity_sha256'] = '4'*64
                    else: manifest['layers'][0]['state'] = 'excluded'
                    new['character-manifest.json'] = raw(manifest)
                elif mutation == 'image': new['images/rest.png'] = b'changed'
                elif mutation == 'geometry':
                    doc = json.loads(new['skeleton.json']); doc['slots'][1]['bone'] = 'other'
                    new['skeleton.json'] = raw(doc)
                elif mutation in ('bones', 'draw_order'):
                    doc = json.loads(new['skeleton.json'])
                    if mutation == 'bones': doc['bones'] = [{'name': 'changed'}]
                    else: doc['animations']['idle']['drawOrder'] = [{'time': 0}]
                    new['skeleton.json'] = raw(doc)
                    ref = json.loads(new['numeric-reference.json'])
                    ref['skeleton_sha256'] = sha256(new['skeleton.json']).hexdigest()
                    new['numeric-reference.json'] = raw(ref)
                elif mutation == 'motion':
                    ref = json.loads(new['numeric-reference.json'])
                    ref['animations']['idle'][0]['vertices']['rest'] = [[5, 6]]
                    new['numeric-reference.json'] = raw(ref)
                elif mutation == 'approval': decisions = [dict(decision, decision_source='automatic')]
                else: decisions *= 2
                with self.assertRaises(ValueError): revalidate(old, new, decisions)


if __name__ == '__main__': unittest.main()
