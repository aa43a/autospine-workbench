from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.affine_leg_ik import solve
from autospine_workbench.targets.character43.affine_pose import matrices


def fixture():
    return dict(bones=[dict(name='root', x=1, y=2, rotation=30, scaleX=1.3, scaleY=.7),
        dict(name='upper', parent='root', x=3, y=4, rotation=20, scaleX=.8, scaleY=1.1),
        dict(name='lower', parent='upper', x=10, y=1, rotation=40, scaleX=1.2, scaleY=.9),
        dict(name='tip', parent='lower', x=8, y=2, rotation=0)],
        animations=dict(move=dict(bones={})))


class AffineLegIkTests(unittest.TestCase):
    def test_recovers_endpoint_under_nonuniform_ancestors_and_keeps_inputs(self):
        doc = fixture(); before = deepcopy(doc); changed = deepcopy(doc)
        changed['animations']['move']['bones'] = {
            'upper': {'rotate': [dict(time=0, value=13)]},
            'lower': {'rotate': [dict(time=0, value=-17)]}}
        target = matrices(changed, 'move', 0)['tip'][4:6]
        report = solve(doc, 'move', 0, 'upper', 'lower', 'tip', target)
        self.assertEqual(doc, before)
        self.assertEqual(report['status'], 'candidate')
        result = deepcopy(doc)
        for bone in ('upper', 'lower'):
            result['animations']['move']['bones'][bone] = {'rotate': [
                dict(time=0, value=report['solution'][bone+'_delta_degrees'])]}
        actual = matrices(result, 'move', 0)['tip'][4:6]
        for a, b in zip(actual, target):
            self.assertAlmostEqual(a, b, places=7)
        self.assertFalse(report['selected'])

    def test_unreachable_does_not_stretch_or_claim_infeasibility(self):
        doc = fixture()
        report = solve(doc, 'move', 0, 'upper', 'lower', 'tip', (10000, 10000))
        self.assertEqual(report['status'], 'no_bounded_solution_found')
        self.assertIsNone(report['solution'])
        self.assertTrue(report['exceeds_outer_reach_bound'])


if __name__ == '__main__':
    unittest.main()
