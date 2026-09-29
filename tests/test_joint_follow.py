from copy import deepcopy
import json
import math
import unittest

from test_joint_secondary import scene
from autospine_workbench.targets.character43.joint_secondary import apply, inventory, normalize
from autospine_workbench.targets.character43.joint_follow import pendulum
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.joint_animation_config import normalize as normalize_joint


def object_scene():
    files, doc = scene()
    manifest = json.loads(files['character-manifest.json'])
    manifest['layers'][-1]['name'] = 'objects'
    files['character-manifest.json'] = json.dumps(manifest).encode()
    return files, doc


class FollowTests(unittest.TestCase):
    def test_pendulum_preserves_every_original_pose_at_zero_response(self):
        _, doc = object_scene(); before = deepcopy(doc)
        record = pendulum(doc, 'hair', .2, .8)
        self.assertEqual(record['root_driver'], 'head')
        self.assertEqual(doc['slots'], before['slots'])
        self.assertEqual(doc['animations'], before['animations'])
        for t in (0, .23, 1.01, 1.73, 2):
            a, b = sample(before, 'idle', t)[0], sample(doc, 'idle', t)[0]
            self.assertLess(max(math.dist(p,q) for p,q in zip(a['hair'], b['hair'])), 1e-8)
        for field in ('uvs', 'triangles', 'path'):
            self.assertEqual(doc['skins'][0]['attachments']['hair']['hair'][field],
                             before['skins'][0]['attachments']['hair']['hair'][field])

    def test_object_motion_anchor_and_source_are_preserved(self):
        files, doc = object_scene(); before = deepcopy(doc)
        config = {'objects': {'enabled': True, 'overrides': {'hair': {'anchor_x': .2, 'anchor_y': .8}}}}
        out, report = apply(files, doc, 'idle', config, [0.,1.,2.])
        self.assertEqual(report['status'], 'applied')
        self.assertEqual(doc, before)
        self.assertLess(report['root_error_px'], 1e-8)
        self.assertGreater(report['regions'][0]['peak_response_deg'], .01)
        self.assertEqual(out['animations'], apply(files,doc,'idle',config,[0.,1.,2.])[0]['animations'])
        self.assertEqual(out['animations']['idle']['bones']['head'], doc['animations']['idle']['bones']['head'])
        for t in (.3, 1.2, 1.9):
            pose = matrices(out,'idle',t); base = matrices(doc,'idle',t)['head']
            x,y = report['regions'][0]['pivot_local']
            self.assertLess(math.dist(pose['m5-object-hair'][4:6],
                (base[4]+base[0]*x+base[1]*y,base[5]+base[2]*x+base[3]*y)), 1e-8)

    def test_existing_repairs_and_multibone_objects_are_not_reassigned(self):
        files, doc = object_scene()
        doc['animations']['idle']['attachments'] = {'default': {'hair': {'hair': {'deform': []}}}}
        self.assertEqual(inventory(files,doc)['objects'][0]['reason'],'joint_follow_existing_deform')
        out, report = apply(files,doc,'idle',{'objects':{'enabled':True}},[0.,2.])
        self.assertEqual(report['status'],'blocked')
        self.assertEqual(out, doc)
        del doc['animations']['idle']['attachments']
        doc['skins'][0]['attachments']['hair']['hair']['vertices'][1] = 0
        self.assertEqual(inventory(files,doc)['objects'][0]['reason'],'joint_follow_multiple_drivers')

    def test_object_and_clothing_toggles_are_independent(self):
        from check_joint_isolation import inspect
        from autospine_workbench.automation.storage_io import canonical_bytes
        files, doc = object_scene(); files['skeleton.json'] = canonical_bytes(doc)
        config = normalize_joint({'objects': {'enabled': True}, 'cloth': {'enabled': True}}, 2.)
        report = inspect(files, config, 'idle', 2.)
        self.assertTrue(report['passed'])
        self.assertEqual(len(report['variants']), 6)
        self.assertTrue(report['surviving_helper_tracks_identical'])

    def test_cascade_changes_tips_not_body_or_root_and_is_seek_independent(self):
        files, doc = scene()
        a, _ = apply(files,doc,'idle',{'hair':{'enabled':True}},[0.,2.])
        b, report = apply(files,doc,'idle',{'hair':{'enabled':True,'cascade':True}},[0.,2.])
        names=report['regions'][0]['helpers']
        self.assertTrue(any(a['animations']['idle']['bones'][n]!=b['animations']['idle']['bones'][n]
                            for n in names if n.endswith('lower')))
        self.assertLess(report['root_error_px'],1e-8)
        self.assertEqual(b['animations']['idle']['bones']['head'],doc['animations']['idle']['bones']['head'])
        self.assertEqual({t:sample(b,'idle',t)[0] for t in (.17,.91,1.7)},
                         {t:sample(b,'idle',t)[0] for t in (1.7,.91,.17)})

    def test_old_config_migrates_with_new_effects_disabled_and_parameters_checked(self):
        cfg=normalize_joint({'hair':{'enabled':True}},2.)
        self.assertFalse(cfg['objects']['enabled']);self.assertFalse(cfg['hair']['cascade'])
        for cfg in ({'objects':{'anchor_x':2}}, {'hair':{'cascade':1}},
                    {'cloth':{'overrides':{'skirt':{'anchor_x':.5}}}},
                    {'objects':{'overrides':{'hair':{'root_fraction':.5}}}}):
            with self.assertRaises(ValueError):normalize(cfg,2.)

    def test_semantic_side_hair_is_discovered_without_guessing_unknown_names(self):
        files,doc=scene();manifest=json.loads(files['character-manifest.json'])
        for name, count in [('side_hair',1),('横髪',1),('unrelated objectish',0)]:
            manifest['layers'][-1]['name']=name;files['character-manifest.json']=json.dumps(manifest).encode()
            self.assertEqual(len(inventory(files,doc)['hair']),count)


if __name__ == '__main__': unittest.main()
