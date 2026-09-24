import unittest
from autospine_workbench.targets.character43.pose_variant_transition import compare_surfaces


class PoseVariantTransitionTests(unittest.TestCase):
    def test_refinement_preserves_material_surface(self):
        a=dict(uvs=[0,0,1,0,0,1],triangles=[0,1,2])
        b=dict(uvs=[0,0,1,0,0,1,1/3,1/3],triangles=[0,1,3,1,2,3,2,0,3])
        result=compare_surfaces(a,[[0,0],[3,0],[0,3]],b,[[0,0],[3,0],[0,3],[1,1]])
        self.assertEqual(result['unresolved'],0)
        self.assertLess(result['maximum_displacement_px'],1e-10)
        moved=compare_surfaces(a,[[0,0],[3,0],[0,3]],b,[[0,0],[3,0],[0,3],[1,2]])
        self.assertAlmostEqual(moved['maximum_displacement_px'],1)

    def test_uv_overlap_is_not_silently_resolved(self):
        a=dict(uvs=[0,0,1,0,0,1],triangles=[0,1,2])
        b=dict(uvs=a['uvs']*2,triangles=[0,1,2,3,4,5])
        result=compare_surfaces(a,[[0,0],[1,0],[0,1]],b,[[0,0],[1,0],[0,1],[2,0],[3,0],[2,1]])
        self.assertEqual(result['unresolved'],result['probes'])
        self.assertIsNone(result['maximum_displacement_px'])

    def test_changed_uv_coverage_stays_unresolved(self):
        a=dict(uvs=[0,0,1,0,0,1],triangles=[0,1,2])
        b=dict(uvs=[2,0,3,0,2,1],triangles=[0,1,2])
        result=compare_surfaces(a,[[0,0],[1,0],[0,1]],b,[[0,0],[1,0],[0,1]])
        self.assertEqual(result['unresolved'],result['probes'])
