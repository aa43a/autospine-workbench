from copy import deepcopy
import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.contact_root_candidate import build


def document():
    return {'bones': [dict(name='root', x=0, y=0, rotation=0)],
            'animations': {'walk': {'bones': {'root': {'translate': [
                dict(time=0, x=0, y=0), dict(time=1, x=10, y=0)]}}}}}


def sample(doc, name, time):
    return {}, {'foot_l': (10*time, 0, 0), 'foot_r': (10*time, 0, 0)}


class ContactRootTests(unittest.TestCase):
    @patch('autospine_workbench.targets.character43.contact_root_candidate.sample', sample)
    def test_corrects_contact_then_releases_without_changing_other_data(self):
        source = document(); before = deepcopy(source)
        result, evidence = build(source, 'walk', [dict(limb='leg.left', start=0, end=.5)],
                                 reference_length=100, samples=11, release_seconds=.2)
        self.assertEqual(source, before)
        self.assertEqual(result['bones'], before['bones'])
        keys = result['animations']['walk']['bones']['root']['translate']
        self.assertTrue(all(abs(k['x']) < 1e-8 for k in keys if k['time'] <= .5))
        self.assertAlmostEqual(keys[-1]['x'], 10)
        self.assertFalse(evidence['selected'])
        self.assertEqual(evidence['status'], 'candidate')

    @patch('autospine_workbench.targets.character43.contact_root_candidate.sample', sample)
    def test_budget_failure_does_not_return_modified_animation(self):
        result, evidence = build(document(), 'walk', [dict(limb='leg.left', start=0, end=1)],
                                 reference_length=10, max_ratio=.1)
        self.assertIsNone(result)
        self.assertEqual(evidence['status'], 'blocked')

    def test_conflicting_double_support_is_not_silently_averaged(self):
        def divergent(doc, name, time):
            return {}, {'foot_l': (time*10, 0, 0), 'foot_r': (-time*10, 0, 0)}
        contacts = [dict(limb='leg.'+s, start=0, end=1) for s in ('left', 'right')]
        with patch('autospine_workbench.targets.character43.contact_root_candidate.sample', divergent):
            result, evidence = build(document(), 'walk', contacts, reference_length=100)
        self.assertIsNone(result)
        self.assertGreater(evidence['max_residual_px'], 1)

    def test_overlapping_same_leg_intervals_rejected(self):
        with self.assertRaisesRegex(ValueError, 'same_limb_overlap'):
            build(document(), 'walk', [dict(limb='leg.left', start=0, end=.8),
                                      dict(limb='leg.left', start=.5, end=1)], reference_length=100)
