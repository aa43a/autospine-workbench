from copy import deepcopy
import math
import unittest
from tests.test_component_weight_transition import limb_fixture
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.component_weight_transition import build as transition_build
from autospine_workbench.asset.planning.component_local_correction import build as correction_build
from autospine_workbench.asset.planning.component_collar import build
from autospine_workbench.asset.planning.component_collar_solver import solve


class ComponentCollarTests(unittest.TestCase):
    def test_collar_capped_against_original_not_accumulated(self):
        mesh=dict(vertices_xy=[[0.,0.],[10.,0.],[10.,10.],[0.,10.]],triangles=[[0,1,2],[0,2,3]])
        bones=[dict(head_xy=[5,-15],tail_xy=[5,5]),dict(head_xy=[5,5],tail_xy=[5,25])]
        original=[[0.,0.],[10.,0.],[10.,1.],[0.,1.]];initial=deepcopy(original)
        revised,info=solve(mesh,original,initial,bones,1)
        self.assertTrue(info['free_vertices'])
        for i in info['free_vertices']:
            self.assertLessEqual(math.dist(revised[i],original[i]),info['budget']+1e-9)
        for i in set(range(4))-set(info['free_vertices']):self.assertEqual(revised[i],initial[i])
        self.assertEqual(solve(mesh,original,initial,bones,0)[0],initial)

    def test_distal_budget_uses_parent_segment_not_short_terminal_bone(self):
        mesh=dict(vertices_xy=[[0.,0.],[10.,0.],[10.,10.],[0.,10.]],triangles=[[0,1,2],[0,2,3]])
        bones=[dict(head_xy=[5,-35],tail_xy=[5,-15]),dict(head_xy=[5,-15],tail_xy=[5,5]),dict(head_xy=[5,5],tail_xy=[5,6])]
        original=[[0.,0.],[10.,0.],[10.,1.],[0.,1.]]
        _,info=solve(mesh,original,original,bones,2)
        self.assertEqual(info['budget'],3.)
        self.assertEqual(info['radius'],9.)

    def test_track_regression_source_binding_and_repeatability(self):
        args=limb_fixture();source=transition_build(mesh_build(*args),args[1],args[0]);correction=correction_build(source,args[1])
        saved=deepcopy(correction);result=build(source,correction,args[1])
        self.assertEqual(correction,saved)
        self.assertEqual(result,build(source,correction,args[1]))
        self.assertFalse(result['production_authorized'])
        for row in result['comparisons']:
            if row['selected']:
                self.assertTrue(all(a<=b for a,b in zip(row['score_after'],row['score_before'])))
                self.assertTrue(all(a['inversions']<=b['inversions'] for a,b in zip(row['trial'],row['before'])))
        correction['source_sha256']='0'*64
        with self.assertRaises(ValueError):build(source,correction,args[1])
