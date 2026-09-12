from copy import deepcopy
import math
import unittest
from autospine_workbench.targets.character43.cloth_rotary_transition import bake
from autospine_workbench.targets.character43.affine_pose import sample


def fixture():
    vertices = []
    for x, y, weight in [(10, 0, .5), (10, 1, .5), (11, 0, .5), (20, 0, 0.)]:
        vertices += [2, 0, x, y, 1-weight, 1, x, y, weight]
    return dict(bones=[dict(name='forearm_l', x=0, y=0, rotation=0),
        dict(name='cloth-fabric', parent='forearm_l', x=0, y=0, rotation=0)],
        skins=[{'attachments': {'fabric': {'fabric': {'vertices': vertices}}}}],
        animations={'wave': {'bones': {
            'forearm_l': {'rotate': [dict(time=0, value=0), dict(time=1, value=180)]},
            'cloth-fabric': {'rotate': [dict(time=0, value=0), dict(time=1, value=-180)]}}}})


class RotaryTests(unittest.TestCase):
    def test_opposed_pair_keeps_radius_and_noncloth_vertex(self):
        doc = fixture(); before = deepcopy(doc)
        result, report = bake(doc, 'wave', ['cloth-fabric'], samples=65)
        original = sample(doc, 'wave', 1)[0]['fabric']
        corrected = sample(result, 'wave', 1)[0]['fabric']
        self.assertLess(math.hypot(*original[0]), 1e-10)
        self.assertAlmostEqual(math.hypot(*corrected[0]), 10)
        self.assertEqual(corrected[3], original[3])
        self.assertEqual(sample(result, 'wave', 0)[0], sample(doc, 'wave', 0)[0])
        self.assertEqual(doc, before)
        self.assertEqual(result, bake(doc, 'wave', ['cloth-fabric'], samples=65)[0])
        self.assertEqual(report['geometry_status'], 'requires_independent_check')

    def test_does_not_overwrite_existing_deform(self):
        doc = fixture(); doc['animations']['wave']['attachments'] = {'default': {'fabric': {}}}
        with self.assertRaisesRegex(ValueError, 'existing_deform'):
            bake(doc, 'wave', ['cloth-fabric'])

    def test_inconsistent_setup_and_curves_rejected(self):
        doc = fixture(); doc['skins'][0]['attachments']['fabric']['fabric']['vertices'][6] += 1
        with self.assertRaisesRegex(ValueError, 'setup_mismatch'):
            bake(doc, 'wave', ['cloth-fabric'])
        doc = fixture(); doc['animations']['wave']['bones']['forearm_l']['rotate'][0]['curve'] = 'stepped'
        with self.assertRaisesRegex(ValueError, 'curve_unsupported'):
            bake(doc, 'wave', ['cloth-fabric'])
