from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.cloth_direction_probe import sweep
from test_character_cloth_rotary import fixture


class ProbeTests(unittest.TestCase):
    def source(self):
        doc = fixture()
        doc['bones'].append(dict(name='hand_l', parent='forearm_l', x=0, y=0, rotation=0))
        del doc['animations']['wave']['bones']['cloth-fabric']
        doc['skins'][0]['attachments']['fabric']['fabric']['triangles'] = [0, 1, 2]
        return doc

    def test_full_hold_exposes_collapse_without_adopting_or_mutating(self):
        doc = self.source(); before = deepcopy(doc)
        report = sweep(doc, 'wave', ['cloth-fabric'], samples=9)
        self.assertEqual(doc, before)
        self.assertTrue(report['records'][0]['geometry_passed'])
        self.assertFalse(report['records'][-1]['geometry_passed'])
        self.assertEqual(report['records'][-1]['slots'][0]['residual_ancestor_rotation_degrees'], 0)
        self.assertFalse(report['selected'])
        self.assertEqual(report['runtime_status'], 'not_evaluated')
        self.assertEqual(report, sweep(doc, 'wave', ['cloth-fabric'], samples=9))

    def test_sample_bounds_and_existing_driver_fail(self):
        for samples in (True, 2, 514):
            with self.assertRaisesRegex(ValueError, 'samples'):
                sweep(self.source(), 'wave', ['cloth-fabric'], samples=samples)
        doc = self.source(); doc['animations']['wave']['bones']['cloth-fabric'] = {}
        with self.assertRaisesRegex(ValueError, 'existing_driver'):
            sweep(doc, 'wave', ['cloth-fabric'])
