import unittest
from autospine_workbench.targets.character43.material_transport_map import build,apply


class MaterialTransportTests(unittest.TestCase):
    def test_identity_and_pose_zero_preserve_one_surface(self):
        uv=[0,0,1,0,0,1];points=[[10,20],[30,20],[10,40]]
        mapping=build(uv,uv,[0,1,2])
        self.assertEqual(apply(points,mapping,1),points)
        shifted=build(uv,[.1,0,1,0,.1,1],[0,1,2])
        self.assertEqual(apply(points,shifted,0),points)
        target=apply(points,shifted,1)
        self.assertAlmostEqual(target[0][0],10-20/9)
        self.assertGreater(shifted['extrapolated_vertices'],0)

    def test_excessive_extrapolation_and_degenerate_uv_rejected(self):
        with self.assertRaisesRegex(ValueError,'extrapolation_limit'):
            build([0,0,1,0,0,1],[.9,0,1,0,.9,1],[0,1,2])
        with self.assertRaisesRegex(ValueError,'degenerate_uv'):
            build([0,0,1,0,0,1],[0,0,0,0,0,1],[0,1,2])

    def test_explicit_partial_mapping_keeps_unsupported_vertices(self):
        m=build([0,0,1,0,0,1],[.9,0,1,0,.9,1],[0,1,2],preserve_unmapped=True)
        self.assertEqual(m['preserved_unmapped_vertices'],[0,2])
        points=[[0,0],[10,0],[0,10]]
        self.assertEqual(apply(points,m,1),points)
