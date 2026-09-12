"""Generic torso/waist differential motion and authority preservation."""
from hashlib import sha256
import importlib.util
import json
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.skirt_candidate import generate
from autospine_workbench.targets.character43.skirt_motion_contact import analyze


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
class SkirtWaistDriverTests(unittest.TestCase):
    def test_torso_translation_tracks_waist_without_moving_hem_or_other_layers(self):
        files = fixture(); doc = json.loads(files['skeleton.json'])
        v = doc['skins'][0]['attachments']['shirt']['shirt']['vertices']
        for i in range(0, len(v), 5): v[i+1] = 4
        doc['animations']['idle']['bones']['chest'] = {'translate': [
            dict(time=0, x=0, y=0), dict(time=1, x=4, y=0), dict(time=2, x=0, y=0)]}
        files['skeleton.json'] = canonical_bytes(doc)
        files['numeric-reference.json'] = canonical_bytes(dict(
            skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), animations={'idle': [
                dict(time=i/8, vertices=sample(doc, 'idle', i/8)[0]) for i in range(17)]}))
        base, _ = generate(files, 'a'*64, ['skirt'])
        changed, report = generate(files, 'a'*64, ['skirt'], waist_driver='reviewed-chest-v1')
        old = analyze(base)['rows'][0]['motions'][0]['peak']['separation_px']
        new = analyze(changed)['rows'][0]['motions'][0]['peak']['separation_px']
        self.assertGreater(old, 3.9); self.assertLess(new, .1)
        self.assertTrue(report['geometry_passed'])
        self.assertFalse(report['selected'])
        a, _ = sample(json.loads(base['skeleton.json']), 'idle', 1)
        b, _ = sample(json.loads(changed['skeleton.json']), 'idle', 1)
        self.assertEqual(a['shirt'], b['shirt'])
        mesh = report['rows'][0]['mesh']; bottom = max(p[1] for p in mesh['vertices'])
        for i, p in enumerate(mesh['vertices']):
            if p[1] == bottom: self.assertEqual(a['skirt'][i], b['skirt'][i])
        self.assertEqual(changed['images/skirt.png'], base['images/skirt.png'])

    def test_unreviewed_driver_is_not_guessed(self):
        with self.assertRaisesRegex(ValueError, 'torso_driver_unsupported'):
            generate(fixture(), 'a'*64, ['skirt'], waist_driver='reviewed-chest-v1')
        with self.assertRaisesRegex(ValueError, 'waist_driver_invalid'):
            generate(fixture(), 'a'*64, ['skirt'], waist_driver='anything')
