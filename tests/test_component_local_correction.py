from copy import deepcopy
import math
import unittest
from tests.test_component_weight_transition import limb_fixture
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.component_weight_transition import build as transition_build
from autospine_workbench.asset.planning.component_local_solver import solve
from autospine_workbench.asset.planning.component_local_correction import build


class ComponentLocalCorrectionTests(unittest.TestCase):
    def square(self):
        return dict(vertices_xy=[[0.,0.],[10.,0.],[10.,10.],[0.,10.]],triangles=[[0,1,2],[0,2,3]],
                    weights=[[dict(weight=.5),dict(weight=.5),dict(weight=0.)] for _ in range(4)])

    def test_area_recovery_is_bounded_deterministic_and_nonmutating(self):
        mesh=self.square(); points=[[0.,0.],[10.,0.],[10.,1.],[0.,1.]]
        before=deepcopy(mesh); original=deepcopy(points)
        result=solve(mesh,points,1,4.)
        self.assertTrue(result['selected'])
        self.assertEqual(result['selected_qa']['bad_triangles'],[])
        self.assertLessEqual(result['max_trial_offset'],4.+1e-9)
        self.assertEqual(solve(mesh,points,1,4.),result)
        self.assertEqual(mesh,before); self.assertEqual(points,original)

    def test_rigid_vertices_and_valid_setup_remain_fixed(self):
        mesh=self.square()
        result=solve(mesh,mesh['vertices_xy'],1,1.)
        self.assertFalse(result['selected']);self.assertEqual(result['points'],mesh['vertices_xy'])
        mesh['weights']=[[dict(weight=1.),dict(weight=0.),dict(weight=0.)] for _ in range(4)]
        collapsed=[[0.,0.],[10.,0.],[10.,1.],[0.,1.]]
        result=solve(mesh,collapsed,1,4.)
        self.assertFalse(result['selected']);self.assertEqual(result['points'],collapsed)
        self.assertEqual(result['free_vertices'],[])
        with self.assertRaises(ValueError):solve(mesh,collapsed,1,math.inf)

    def test_source_binding_and_per_pose_conservation(self):
        args=limb_fixture(); source=transition_build(mesh_build(*args),args[1],args[0])
        result=build(source,args[1]); self.assertEqual(result,build(source,args[1]))
        self.assertFalse(result['production_authorized'])
        self.assertEqual(result['temporal_status'],'independent_probe_poses_only')
        for row in result['rows']:
            for pose in row['poses']:
                self.assertLessEqual(pose['selected_qa']['inversions'],pose['before_qa']['inversions'])
                self.assertTrue(set(pose['selected_qa']['bad_triangles'])<=set(pose['before_qa']['bad_triangles']))
        source['skeleton_sha256']='0'*64
        with self.assertRaises(ValueError):build(source,args[1])
