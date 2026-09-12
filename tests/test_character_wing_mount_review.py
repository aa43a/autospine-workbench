"""Existing component analysis keeps source coordinates and approval separate."""
import importlib.util
import json
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.targets.character43.wing_mount_review import build


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
class WingMountReviewTests(unittest.TestCase):
    def test_source_unchanged_and_exact_image_alignment(self):
        files=fixture(); manifest=json.loads(files['character-manifest.json'])
        manifest['layers'][0]['name']='wings'
        files['character-manifest.json']=json.dumps(manifest).encode()
        before=dict(files); outputs=build(files)
        self.assertEqual(files,before)
        report=json.loads(outputs['report.json'])
        self.assertFalse(report['selected'])
        self.assertEqual(report['rows'][0]['components'][0]['area_pixels'],8000)
        self.assertEqual(report['rows'][0]['components'][0]['projected_target_coverage'],.4)
        self.assertIn(b'x="-40" y="0" width="80" height="100"',outputs['index.html'])
        self.assertIn(files['images/skirt.png'],outputs.values())
        self.assertEqual(outputs,build(files))

    def test_missing_semantic_scope_does_not_guess_wings(self):
        with self.assertRaisesRegex(ValueError,'source_missing'):
            build(fixture())
