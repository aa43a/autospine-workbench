import unittest
import json

from autospine_workbench.targets.character43.shoulder_boundary import prepare
from autospine_workbench.targets.character43.deform_addition import add, value
from autospine_workbench.targets.character43.shoulder_boundary_adaptive import generate


class ShoulderBoundaryTests(unittest.TestCase):
    def test_contact_selection_is_scale_and_translation_invariant(self):
        points = [[x, y] for y in range(5) for x in range(3)]
        triangles = []
        for y in range(4):
            for x in range(2):
                a = 3*y+x
                triangles.extend([[a, a+1, a+3], [a+1, a+4, a+3]])
        contact = [[0, 0], [1, 0], [2, 0]]
        first = prepare(points, triangles, contact, [1, 0], [1, 4])
        move = lambda p: [p[0]*7+23, p[1]*7-19]
        second = prepare(list(map(move, points)), triangles, list(map(move, contact)), move([1, 0]), move([1, 4]))
        self.assertEqual(first['pins'], second['pins'])
        self.assertEqual(first['free'], second['free'])
        self.assertAlmostEqual(first['budget_px']*7, second['budget_px'])
        self.assertFalse(set(first['pins']) & set(first['free']))
        self.assertFalse(set(first['pins']) & {4, 7, 10})  # Interior vertices cannot be boundary pins.
        mirror = lambda p: [-p[0], p[1]]
        mirrored = prepare(list(map(mirror, points)), triangles, list(map(mirror, contact)), mirror([1, 0]), mirror([1, 4]))
        self.assertEqual(first['pins'], mirrored['pins'])
        self.assertEqual(first['free'], mirrored['free'])

    def test_additive_keys_preserve_original_motion_at_unrelated_offsets(self):
        old = [dict(time=0, offset=2, vertices=[2, 4]), dict(time=.4, vertices=[3, 5, 4, 8]),
               dict(time=1, vertices=[7, 9, 6, 12])]
        correction = [dict(time=0, vertices=[0, 0, 0, 0]),
                      dict(time=.7, vertices=[1, 2, 0, 0]), dict(time=1, vertices=[0, 0, 0, 0])]
        combined = add(old, correction, 4)
        self.assertEqual([k['time'] for k in combined], [0, .4, .7, 1])
        for i in range(101):
            t = i/100
            expected = [a+b for a, b in zip(value(old, t, 4), value(correction, t, 4))]
            for a, b in zip(expected, value(combined, t, 4)):
                self.assertAlmostEqual(a, b)
            for a, b in zip(value(old, t, 4)[2:], value(combined, t, 4)[2:]):
                self.assertAlmostEqual(a, b, places=12)

    def test_non_linear_deform_is_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError, 'non_linear'):
            add([dict(time=0, curve='stepped', vertices=[1, 2])], [dict(time=0, vertices=[0, 0])], 2)

    def test_adaptive_trial_cannot_cross_source_identity(self):
        trial = {'shoulder-boundary-trial.json': json.dumps(dict(
            profile='proximal-contact-pinned-shape-v1', source_character_sha256='a'*64)).encode()}
        with self.assertRaisesRegex(ValueError, 'source_mismatch'):
            generate({}, 'b'*64, trial, 'c'*64)


if __name__ == '__main__':
    unittest.main()
