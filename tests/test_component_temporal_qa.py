from copy import deepcopy
import unittest
from tests.test_component_weight_transition import limb_fixture
from autospine_workbench.asset.planning.component_mesh import build as mesh_build
from autospine_workbench.asset.planning.component_weight_transition import build as transition_build
from autospine_workbench.asset.planning.component_local_correction import build as correction_build
from autospine_workbench.asset.planning.component_temporal_qa import build,sample,velocity_jump,passed
from autospine_workbench.asset.planning.component_local_solver import metrics


class ComponentTemporalTests(unittest.TestCase):
    def test_interpolation_detects_collapsed_middle_with_valid_endpoints(self):
        setup=[[0,0],[2,0],[0,2]];end=[[0,0],[-2,0],[0,-2]];triangles=[[0,1,2]]
        self.assertTrue(passed(metrics(setup,setup,triangles)))
        self.assertTrue(passed(metrics(setup,end,triangles)))
        self.assertFalse(passed(metrics(setup,sample([setup,end],.5),triangles)))
        self.assertEqual(sample([setup,end],-1),setup)
        self.assertEqual(sample([setup,end],3),end)

    def test_track_boundaries_sources_and_determinism(self):
        args=limb_fixture(); source=transition_build(mesh_build(*args),args[1],args[0])
        correction=correction_build(source,args[1]); before=deepcopy(correction)
        result=build(source,correction,args[1])
        self.assertEqual(build(source,correction,args[1]),result)
        self.assertEqual(before,correction)
        self.assertEqual(len(result['rows']),3)
        self.assertTrue(all(len(r['ticks'])==33 for r in result['rows']))
        self.assertFalse(result['continuous_time_proven'])
        correction['source_sha256']='0'*64
        with self.assertRaises(ValueError):build(source,correction,args[1])

    def test_velocity_break_is_measured_without_claiming_smoothness(self):
        self.assertEqual(velocity_jump([[[0,0]],[[1,0]],[[2,0]]]),0)
        self.assertEqual(velocity_jump([[[0,0]],[[1,0]],[[3,0]]]),1)
