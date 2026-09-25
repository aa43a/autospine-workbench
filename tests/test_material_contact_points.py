import unittest
from copy import deepcopy
import numpy as np
from autospine_workbench.targets.character43.material_contact_points import bind, sample


class MaterialContactPointTests(unittest.TestCase):
    def setUp(self):
        self.points=[[0,0],[10,0],[10,10],[0,10]]
        self.triangles=[[0,1,2],[0,2,3]]

    def test_setup_and_affine_motion_preserve_material_location(self):
        probes=[[2,1],[2,8],[5,5],[0,0]]
        binding=bind(self.points,self.triangles,probes)
        np.testing.assert_allclose(sample(binding,self.points,self.triangles),probes,atol=1e-10)
        a=np.array([[.6,-.2],[.3,1.2]]); offset=[31,-8]
        world=np.asarray(self.points)@a.T+offset
        np.testing.assert_allclose(sample(binding,world,self.triangles),np.asarray(probes)@a.T+offset)

    def test_nonrigid_motion_uses_three_vertices_not_nearest_vertex(self):
        binding=bind(self.points,self.triangles,[[2,1]])
        world=deepcopy(self.points);world[2]=[10,20]
        np.testing.assert_allclose(sample(binding,world,self.triangles),[[2,2]])

    def test_outside_and_ambiguous_points_not_extrapolated(self):
        for point in ([-1,2],[11,2]):
            with self.assertRaisesRegex(ValueError,'outside_mesh'):bind(self.points,self.triangles,[point])
        with self.assertRaisesRegex(ValueError,'overlapping_mesh'):
            bind(self.points,[[0,1,2],[0,1,2]],[[2,1]])
        # A point on one triangle's edge but inside another is not a shared edge.
        with self.assertRaisesRegex(ValueError,'overlapping_mesh'):
            bind(self.points+[[2,0],[2,3],[4,3]],self.triangles+[[4,5,6]],[[2,1]])

    def test_topology_change_requires_rebinding(self):
        binding=bind(self.points,self.triangles,[[2,1]])
        with self.assertRaisesRegex(ValueError,'topology_changed'):
            sample(binding,self.points,list(reversed(self.triangles)))
        binding['records'][0]['weights']=[-1,1,1]
        with self.assertRaisesRegex(ValueError,'binding_invalid'):sample(binding,self.points,self.triangles)

    def test_invalid_and_degenerate_inputs(self):
        with self.assertRaisesRegex(ValueError,'outside_mesh'):
            bind([[0,0],[1,0],[2,0]],[[0,1,2]],[[1,0]])
        for triangles in ([[0.,1.,2.]],[[0,1,4]]):
            with self.assertRaisesRegex(ValueError,'mesh_invalid'):bind(self.points,triangles,[[2,1]])
        with self.assertRaisesRegex(ValueError,'locations_invalid'):
            bind(self.points,self.triangles,[[float('nan'),0]])
