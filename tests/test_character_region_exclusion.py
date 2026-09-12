from hashlib import sha256
import json
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.targets.character43.region_exclusion import apply


def fixture():
    skeleton = dict(slots=[{'name': n} for n in ('leg', 'rest')],
                    skins=[{'attachments': {n: {n: {'path': n}} for n in ('leg', 'rest')}}], animations={'idle': {}})
    manifest = dict(layers=[dict(layer_id='source', regions=[dict(region_id='leg', state='weighted_candidate'),
                    dict(region_id='rest', state='static_reference')], reason_codes=['static_reference_not_bound'],
                    missing_region_ids=[], state='partial')])
    files = {'skeleton.json': raw(skeleton), 'editor/skeleton.json': raw(skeleton),
             'character-manifest.json': raw(manifest), 'images/rest.png': b'original', 'skeleton.atlas': b'atlas'}
    files['numeric-reference.json'] = raw(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        animations={'idle': [dict(time=0, vertices={'leg': [[1, 2]], 'rest': [[3, 4]]})]}))
    decision = dict(schema='autospine.region-exclusion/v1', decision_source='human_confirmation',
                    manifest_sha256=sha256(files['character-manifest.json']).hexdigest(), layer_id='source',
                    region_id='rest', image_sha256=sha256(b'original').hexdigest())
    return files, decision


class ExclusionTests(unittest.TestCase):
    def test_only_confirmed_static_region_removed_and_other_geometry_preserved(self):
        files, decision = fixture(); before = dict(files); result = apply(files, decision)
        self.assertEqual(files, before)
        self.assertEqual(json.loads(result['skeleton.json'])['slots'], [{'name': 'leg'}])
        self.assertEqual(json.loads(result['numeric-reference.json'])['animations']['idle'][0]['vertices'], {'leg': [[1, 2]]})
        self.assertEqual(result['images/rest.png'], b'original')
        manifest = json.loads(result['character-manifest.json'])
        self.assertFalse(manifest['production_authorized'])
        self.assertEqual(manifest['qa']['runtime_status'], 'not_run')

    def test_stale_or_unconfirmed_decision_rejected(self):
        files, decision = fixture()
        for key, value in [('manifest_sha256', '0'*64), ('image_sha256', '0'*64),
                           ('decision_source', 'automatic'), ('region_id', 'leg')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                apply(files, {**decision, key: value})

    def test_draw_order_dependency_cannot_be_silently_reindexed(self):
        files, decision = fixture(); doc = json.loads(files['skeleton.json'])
        doc['animations']['idle']['drawOrder'] = [{'time': 0}]
        files['skeleton.json'] = raw(doc); ref = json.loads(files['numeric-reference.json'])
        ref['skeleton_sha256'] = sha256(files['skeleton.json']).hexdigest(); files['numeric-reference.json'] = raw(ref)
        with self.assertRaisesRegex(ValueError, 'animated_dependency'):
            apply(files, decision)
