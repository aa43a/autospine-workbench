import unittest
from autospine_workbench.targets.character43.deform_sum import combine
from autospine_workbench.targets.spine43.continuous_pose import interpolate


class DeformSumTests(unittest.TestCase):
    def test_preserves_interleaved_extrema_at_arbitrary_times(self):
        old = [dict(time=0, vertices=[0., 0.]), dict(time=.3, vertices=[10., -2.]),
               dict(time=.6, vertices=[-3., 7.]), dict(time=1, vertices=[0., 0.])]
        delta = [dict(time=0, vertices=[0., 0.]), dict(time=.5, vertices=[2., 0.]),
                 dict(time=1, vertices=[0., 0.])]
        result = combine(old, delta)
        self.assertEqual([k['time'] for k in result], [0, .3, .5, .6, 1])
        for i in range(101):
            t = i/100
            expected = [a+b for a, b in zip(interpolate(old, t, 'vertices'), interpolate(delta, t, 'vertices'))]
            for a, b in zip(expected, interpolate(result, t, 'vertices')):
                self.assertAlmostEqual(a, b, places=12)

    def test_does_not_silently_resample_curved_keys(self):
        old = [dict(time=0, vertices=[0., 0.], curve='stepped'), dict(time=1, vertices=[1., 1.])]
        with self.assertRaisesRegex(ValueError, 'curve_unsupported'): combine(old, old)
