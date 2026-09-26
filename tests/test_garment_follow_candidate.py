from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.garment_follow_scope import resolve
from autospine_workbench.targets.character43.garment_follow_candidate import build
from autospine_workbench.targets.character43.numeric_reference import read
from test_attachment_root_bake import fixture


def bundle():
    doc, torso = fixture()
    doc['bones'][2]['name'] = 'garment-center_upper'
    doc['bones'][3]['parent'] = 'garment-center_upper'
    doc['animations']['motion']['attachments']['default']['body'] = {'body': {'deform': [
        dict(time=0, vertices=[0]*6), dict(time=1, vertices=[0, 0, -2, 2, 2, -2])]}}
    raw = canonical_bytes(doc); digest = sha256(raw).hexdigest()
    setup = sample(dict(doc, animations={'setup': {}}), 'setup', 0)[0]
    files = {'skeleton.json': raw, 'motion-torso-projection.json': canonical_bytes(torso),
        'rig-setup-reference.json': canonical_bytes(dict(skeleton_sha256=digest, vertices=setup)),
        'numeric-reference.json': canonical_bytes(dict(skeleton_sha256=digest,
            animations={'motion': [dict(time=t) for t in [0, 1]]})),
        'motion-review.json': canonical_bytes(dict(reference_length_px=10, status='accepted', selected=True,
            issues=[dict(stage='depth', reason_code='old')])),
        'motion-contact.json': b'{}', 'motion-ir.json': b'{}', 'deformation.json': b'{"passed":true}',
        'motion-depth.json': b'old', 'images/garment.png': b'original', 'skeleton.atlas': b'atlas',
        'character-manifest.json': b'{"selected":true}'}
    character = dict(files, **{'skirt-trial.json': canonical_bytes(dict(waist_driver='reviewed-chest-v1',
        rows=[dict(layer_id='garment', mesh=dict(helper_chains=[dict(id='center')]))]))})
    return files, character


class GarmentCandidateTests(unittest.TestCase):
    def test_declaration_is_exact_and_does_not_guess_undeclared_or_shared_weights(self):
        files, character = bundle(); scope = resolve(files, character, 'garment', 'motion')
        self.assertEqual(scope['roots'], ['garment-center_upper'])
        with self.assertRaisesRegex(ValueError, 'slot_undeclared'):
            resolve(files, character, 'body', 'motion')
        changed = dict(files); doc = json.loads(files['skeleton.json']); doc['bones'][0]['x'] = 9
        changed['skeleton.json'] = canonical_bytes(doc)
        with self.assertRaisesRegex(ValueError, 'bind_changed'):
            resolve(changed, character, 'garment', 'motion')
        doc = json.loads(files['skeleton.json']); doc['skins'][0]['attachments']['body']['body']['vertices'][1] = 2
        for f in (files, character):
            f['skeleton.json'] = canonical_bytes(doc)
            for key in ('numeric-reference.json', 'rig-setup-reference.json'):
                value = json.loads(f[key]); value['skeleton_sha256'] = sha256(f['skeleton.json']).hexdigest()
                f[key] = canonical_bytes(value)
        with self.assertRaisesRegex(ValueError, 'shared_or_missing'):
            resolve(files, character, 'garment', 'motion')

    def test_builder_keeps_other_failures_and_rechecks_same_grid_without_inherited_approval(self):
        files, character = bundle(); before = deepcopy(files)
        plan = dict(slot='garment', animation='motion', garment_follow=resolve(files, character, 'garment', 'motion'))
        pair = dict(torso='body', skirt_anchor=([0], [1]), torso_anchor=([0], [1]))
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck', return_value={'status':'unavailable'}), \
             patch('autospine_workbench.targets.character43.garment_follow_contact.anchors', return_value=[pair]):
            output, evidence, geometry = build(files, character, plan)
        self.assertEqual(files, before)
        original, actual = (json.loads(f['skeleton.json']) for f in (files, output))
        self.assertEqual(original['bones'], actual['bones']); self.assertEqual(original['skins'], actual['skins'])
        self.assertEqual(original['animations']['motion']['attachments']['default']['body'],
                         actual['animations']['motion']['attachments']['default']['body'])
        self.assertFalse(evidence['selected']); self.assertEqual(evidence['status'], 'needs_changes')
        self.assertEqual(evidence['runtime_status'], 'not_evaluated')
        self.assertNotIn('motion-depth.json', output)
        self.assertEqual(output['motion-torso-projection.json'],files['motion-torso-projection.json'])
        self.assertEqual(output['images/garment.png'], b'original')
        self.assertFalse(next(r for r in geometry['records'] if r['slot']=='body')['passed'])
        report = json.loads(output['motion-repair.json'])
        self.assertEqual(report['geometry']['records'][0]['sample_count'], report['parent_geometry']['records'][0]['sample_count'])
        self.assertEqual(report['garment_follow']['waist_contact']['status'], 'measured')
        self.assertTrue({0, 1} <= {r['time'] for r in read(output)['animations']['motion']})
        plan['garment_follow']['roots'] = ['tip']
        with self.assertRaisesRegex(ValueError, 'scope_changed'):
            build(files, character, plan)

    def test_missing_torso_invalid_profile_and_nonlinear_deform_fail_explicitly(self):
        files, character = bundle()
        del files['motion-torso-projection.json']
        with self.assertRaisesRegex(ValueError, 'torso_required'):
            resolve(files, character, 'garment', 'motion')
        files, character = bundle(); torso=json.loads(files['motion-torso-projection.json'])
        torso['source']['records'][1]['transverse']=.2; files['motion-torso-projection.json']=canonical_bytes(torso)
        with self.assertRaisesRegex(ValueError, 'source_limits'):
            resolve(files, character, 'garment', 'motion')
        files, character = bundle(); doc=json.loads(files['skeleton.json'])
        doc['animations']['motion']['attachments']['default']['garment']['garment']['deform'][0]['curve']='stepped'
        files['skeleton.json']=canonical_bytes(doc)
        for key in ('numeric-reference.json','rig-setup-reference.json'):
            value=json.loads(files[key]);value['skeleton_sha256']=sha256(files['skeleton.json']).hexdigest();files[key]=canonical_bytes(value)
        with self.assertRaisesRegex(ValueError, 'dense_linear'):
            resolve(files, character, 'garment', 'motion')

    def test_chained_sampling_preserves_dense_qa_without_baking_it_as_animation_keys(self):
        files,character=bundle();reference=json.loads(files['numeric-reference.json'])
        times=[i/3000 for i in range(3001)]
        reference['animations']['motion']=[dict(time=t) for t in times]
        files['numeric-reference.json']=canonical_bytes(reference)
        scope=resolve(files,character,'garment','motion',stable_sampling=True)
        self.assertEqual(scope['bake_sample_count'],3)
        plan=dict(slot='garment',animation='motion',garment_follow=scope)
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'unavailable'}):
            output,_,_=build(files,character,plan)
        actual={r['time'] for r in read(output)['animations']['motion']}
        self.assertTrue(set(times)<=actual);self.assertLessEqual(len(actual),4097)
        self.assertEqual(json.loads(output['motion-garment-follow.json'])['key_samples'],3)
