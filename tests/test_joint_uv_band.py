import unittest
from autospine_workbench.targets.character43.joint_uv_band import contract


class JointUVBandTests(unittest.TestCase):
    def test_bounded_and_local_without_uv_fold(self):
        uv=[.1,0,.9,0,.1,.5,.9,.5,.1,1,.9,1]
        out,report=contract(uv,[0,1,2,1,3,2,2,3,4,3,5,4],[100,100],[50,50],[0,1],30)
        self.assertEqual(out[:4],uv[:4]);self.assertEqual(out[-4:],uv[-4:])
        self.assertLessEqual(report['maximum_displacement_px'],16)
        self.assertGreater(report['minimum_uv_area_ratio'],0)
        self.assertFalse(report['selected'])
        self.assertGreater(out[4],uv[4]);self.assertLess(out[6],uv[6])

    def test_invalid_axis_rejected(self):
        with self.assertRaisesRegex(ValueError,'input'):
            contract([0,0,1,0,0,1],[0,1,2],[100,100],[50,50],[0,0],20)

    def test_nonfinite_radius_and_zero_texture_rejected(self):
        for size,radius in [([100,100],float('nan')),([0,100],20)]:
            with self.assertRaisesRegex(ValueError,'input'):
                contract([0,0,1,0,0,1],[0,1,2],size,[50,50],[0,1],radius)
