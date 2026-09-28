import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.affine_pose import _pair
from autospine_workbench.targets.spine43.continuous_pose import interpolate


class PairSamplingTests(unittest.TestCase):
    def test_exact_match_with_vector_timeline(self):
        for curve in (None, 'stepped'):
            keys = [dict(time=i/30, x=i*.13, y=-i*.17,
                         **({'curve': curve} if curve else {})) for i in range(225)]
            vectors = [dict(time=k['time'], vertices=[k['x'], k['y']],
                            **({'curve': curve} if curve else {})) for k in keys]
            for time in (-.1, 0, .013, .1, 1, 4.23, 7.4666666667, 8):
                self.assertEqual(_pair(keys, time), interpolate(vectors, time, 'vertices'))

    def test_shear_defaults_and_duplicate_keys(self):
        keys = [dict(time=0,x=4), dict(time=.5,y=3), dict(time=.5,x=2)]
        vectors = [dict(time=k['time'], vertices=[k.get('x',0),k.get('y',0)]) for k in keys]
        for time in (0,.25,.5,1):
            self.assertEqual(_pair(keys,time,0),interpolate(vectors,time,'vertices'))

    def test_required_channels_still_fail(self):
        with self.assertRaises(KeyError): _pair([dict(time=0,x=1)],0)

    def test_sample_exposes_same_fk_without_recomputation(self):
        from test_character_affine_repair import fixture
        from autospine_workbench.targets.character43.affine_pose import sample, sample_with_matrices, matrices
        doc=fixture()
        expected=sample(doc,'walk',.5)
        with patch('autospine_workbench.targets.character43.affine_pose.matrices',wraps=matrices) as count:
            result=sample_with_matrices(doc,'walk',.5)
        self.assertEqual(result[:2],expected)
        self.assertEqual(result[2],matrices(doc,'walk',.5))
        self.assertEqual(count.call_count,1)
