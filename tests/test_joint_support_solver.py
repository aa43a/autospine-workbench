from copy import deepcopy
import unittest

from test_affine_leg_ik import fixture
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.joint_support_solver import solve


class JointSupportTests(unittest.TestCase):
    def test_joint_solution_matches_full_affine_fk_without_mutation(self):
        doc = fixture(); before = deepcopy(doc)
        target = matrices(doc, 'move', 0)['tip'][4:6]
        target = [target[0]+2, target[1]-1]
        report = solve(doc, 'move', 0, [dict(upper='upper', lower='lower', tip='tip', target=target)], 30)
        self.assertEqual(doc, before)
        solution = report['solution']; self.assertIsNotNone(solution)
        changed = deepcopy(doc); leg = solution['legs'][0]
        changed['animations']['move']['bones'] = {
            'root': {'translate': [dict(time=0, x=solution['root_shift'][0], y=solution['root_shift'][1])]},
            'upper': {'rotate': [dict(time=0, value=leg['upper_delta_degrees'])]},
            'lower': {'rotate': [dict(time=0, value=leg['lower_delta_degrees'])]}}
        actual = matrices(changed, 'move', 0)['tip'][4:6]
        import math
        self.assertAlmostEqual(math.dist(actual, target), leg['endpoint_error_px'], places=8)
        self.assertLess(math.dist(actual, target), .3)

    def test_unreachable_remains_unresolved_without_stretch(self):
        report = solve(fixture(), 'move', 0,
                       [dict(upper='upper', lower='lower', tip='tip', target=[10000, 0])], 30)
        self.assertIsNone(report['solution'])
        self.assertEqual(report['status'], 'no_bounded_solution_found')

    def test_two_contacts_use_one_root_shift(self):
        doc = fixture()
        for name, parent in [('upper2', 'root'), ('lower2', 'upper2'), ('tip2', 'lower2')]:
            source = next(b for b in doc['bones'] if b['name'] == name[:-1])
            doc['bones'].append(dict(source, name=name, parent=parent))
        pose = matrices(doc, 'move', 0)
        contacts = [dict(upper='upper'+suffix, lower='lower'+suffix, tip='tip'+suffix,
                         target=[pose['tip'+suffix][4]+1, pose['tip'+suffix][5]]) for suffix in ('', '2')]
        report = solve(doc, 'move', 0, contacts, 30)
        self.assertEqual(len(report['solution']['legs']), 2)
        self.assertLess(max(v['endpoint_error_px'] for v in report['solution']['legs']), .3)

    def test_previous_root_enforces_actual_speed(self):
        import math
        doc = fixture(); tip = matrices(doc, 'move', 0)['tip'][4:6]
        report = solve(doc, 'move', .01,
                       [dict(upper='upper', lower='lower', tip='tip', target=[tip[0]+.5, tip[1]])],
                       30, previous=dict(time=0, root_shift=[0, 0]))
        self.assertIsNotNone(report['solution'])
        self.assertLessEqual(math.hypot(*report['solution']['root_shift'])/.01, 60)
        with self.assertRaisesRegex(ValueError, 'previous_invalid'):
            solve(doc, 'move', 0, [dict(upper='upper', lower='lower', tip='tip', target=tip)],
                  30, previous=dict(time=0, root_shift=[0, 0]))

    def test_rotation_speed_caps_recomputed_solution(self):
        doc = fixture(); target = matrices(doc, 'move', 0)['tip'][4:6]
        prior = dict(time=0, root_shift=[0, 0], legs=[dict(upper='upper', lower='lower', tip='tip',
                     upper_delta_degrees=0, lower_delta_degrees=0)])
        result = solve(doc, 'move', .001, [dict(upper='upper', lower='lower', tip='tip',
                       target=[target[0]+.01, target[1]])], 30, previous=prior, maximum_rotation_speed=180)
        self.assertIsNotNone(result['solution'])
        for key in ('upper_delta_degrees', 'lower_delta_degrees'):
            self.assertLessEqual(abs(result['solution']['legs'][0][key])/.001, 180)
