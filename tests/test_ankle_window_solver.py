from copy import deepcopy
import math
import unittest

from test_moving_ankle_candidate import fixture
from autospine_workbench.targets.character43.ankle_window_solver import solve_window
from autospine_workbench.targets.character43.affine_pose import matrices


class AnkleWindowTests(unittest.TestCase):
    def test_window_matches_independent_fk_and_preserves_inputs(self):
        doc, trajectory = fixture()
        before = deepcopy(doc)
        times = [0., .5, 1.]
        start = trajectory[0]['targets']
        targets = [[[p[0]+.2*t, p[1]+.1*t] for p in start] for t in times]
        report = solve_window(doc, 'move', times, targets, 20)
        self.assertEqual(doc, before)
        self.assertFalse(report['selected'])
        self.assertIsNotNone(report['solution'])
        previous = None
        for t, target, values in zip(times, targets, report['solution']):
            changed = deepcopy(doc)
            tracks = changed['animations']['move']['bones']
            tracks['root']['translate'] = [dict(time=0, x=values[0]*20, y=values[1]*20)]
            for i, bone in enumerate(('thigh_l', 'calf_l', 'thigh_r', 'calf_r')):
                tracks[bone] = dict(rotate=[dict(time=0, value=math.degrees(values[i+2]))])
            pose = matrices(changed, 'move', t)
            for i, side in enumerate(('l', 'r')):
                self.assertLessEqual(math.dist(pose['foot_'+side][4:6], target[i]), .2)
            self.assertLessEqual(math.hypot(*values[:2]), .15)
            if previous:
                self.assertLessEqual(math.dist(values[:2], previous[1][:2]), 2*(t-previous[0]))
                self.assertLessEqual(max(abs(a-b) for a, b in zip(values[2:], previous[1][2:])), math.pi*(t-previous[0]))
            previous = t, values

    def test_unreachable_window_returns_no_partial_solution(self):
        doc, trajectory = fixture()
        result = solve_window(doc, 'move', [0., 1.], [trajectory[0]['targets'], [[10000., 0.]]*2], 20)
        self.assertIsNone(result['solution'])
        self.assertEqual(result['status'], 'no_bounded_path_found')

    def test_invalid_window_rejected(self):
        doc, trajectory = fixture()
        with self.assertRaisesRegex(ValueError, 'input_invalid'):
            solve_window(doc, 'move', [0., 0.], [r['targets'] for r in trajectory], 20)

    def test_missing_original_knot_cannot_silently_change_base_animation(self):
        doc, trajectory = fixture()
        doc['animations']['move']['bones']['root']['translate'].insert(1, dict(time=.3, x=1, y=0))
        with self.assertRaisesRegex(ValueError, 'missing_source_knot'):
            solve_window(doc, 'move', [0., 1.], [r['targets'] for r in trajectory], 20)

    def test_interpolated_track_checked_with_full_fk(self):
        doc, trajectory = fixture()
        report = solve_window(doc, 'move', [0., 1.], [r['targets'] for r in trajectory], 20)
        self.assertEqual(report['constraint_times'], [0., .25, .5, .75, 1.])
        values = report['solution']
        self.assertIsNotNone(values)
        tracks = doc['animations']['move']['bones']
        tracks['root']['translate'] = [dict(time=t, x=v[0]*20, y=v[1]*20) for t, v in zip((0., 1.), values)]
        for i, bone in enumerate(('thigh_l', 'calf_l', 'thigh_r', 'calf_r')):
            tracks[bone] = dict(rotate=[dict(time=t, value=math.degrees(v[i+2])) for t, v in zip((0., 1.), values)])
        for n in range(9):
            t = n/8
            pose = matrices(doc, 'move', t)
            for i, side in enumerate(('l', 'r')):
                p = trajectory[0]['targets'][i]
                self.assertLessEqual(math.dist(pose['foot_'+side][4:6], [p[0]+.2*t, p[1]+.1*t]), .2)
