import unittest
import numpy as np
from m4_clip_switch_measure import measure


class ClipSwitchMeasureTests(unittest.TestCase):
    def test_invisible_rgb_does_not_count_as_flash(self):
        a=np.array([[[255,0,0,0]]],dtype=float);b=np.zeros((1,1,4))
        self.assertEqual(measure(a,b)['changed_over_eight'],0)

    def test_alpha_change_counts(self):
        a=np.zeros((1,1,4));b=np.array([[[0,0,0,32]]],dtype=float)
        self.assertEqual(measure(a,b)['changed_over_eight'],1)
        self.assertEqual(measure(a,b)['maximum_alpha_delta'],32)
