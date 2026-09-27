import unittest
from autospine_workbench.targets.character43.parent_setup_preservation import floors
from autospine_workbench.targets.character43.parent_pose_area_repair import solve
from autospine_workbench.targets.spine43.continuous_pose import area


class ParentSetupPreservationTests(unittest.TestCase):
    def test_does_not_invent_headroom_on_valid_fixed_parent(self):
        parent=[[0,0],[2,0],[0,.501]]
        values,_=floors(parent,[[0,1,2]],[.501],[1.])
        self.assertEqual(values,[1.])

    def test_healthy_setup_floor_is_not_capped_to_projected_reference(self):
        parent=[[0,0],[2,0],[0,.8]]
        values,protected=floors(parent,[[0,1,2]],[.3],[1.])
        self.assertEqual(protected,[0]);self.assertAlmostEqual(values[0],.505/.3)

    def test_retains_compression_floor_and_rejects_incompatible_bounds(self):
        values,protected=floors([[0,0],[2,0],[0,.4]],[[0,1,2]],[.3],[1.])
        self.assertEqual(protected,[]);self.assertAlmostEqual(values[0],.4/.3)
        with self.assertRaisesRegex(ValueError,'conflicts_with_projected_ceiling'):
            floors([[0,0],[2,0],[0,.8]],[[0,1,2]],[.2],[1.])

    def test_joint_floor_repairs_healthy_region_missed_by_parent_only(self):
        parent=[[0,0],[2,0],[1,.8]];origin=[[0,0],[2,0],[1,.4]]
        context=dict(row={'triangles':[[0,1,2]]},areas=[.3],edges=[],lengths=[],
                     free=[False,False,True],budget=.2)
        old,_=solve(context,origin,parent,[1.])
        joint,evidence=solve(context,origin,parent,[1.],protect_setup=True)
        self.assertLess(area(old,[0,1,2]),.5)
        self.assertGreaterEqual(area(joint,[0,1,2]),.5)
        self.assertEqual(joint[:2],origin[:2]);self.assertTrue(evidence['converged'])

    def test_fixed_failure_is_not_granted_success(self):
        context=dict(row={'triangles':[[0,1,2]]},areas=[.3],edges=[],lengths=[],free=[False]*3,budget=.2)
        origin=[[0,0],[2,0],[1,.4]]
        joint,evidence=solve(context,origin,[[0,0],[2,0],[1,.8]],[1.],protect_setup=True)
        self.assertEqual(joint,origin);self.assertFalse(evidence['converged'])

    def test_refinement_cannot_turn_fixed_counterexample_into_success(self):
        context=dict(row={'triangles':[[0,1,2]]},areas=[.3],edges=[(0,1),(1,2),(0,2)],lengths=[2,2,2],free=[False]*3,budget=.2)
        origin=[[0,0],[2,0],[1,.4]]
        joint,evidence=solve(context,origin,[[0,0],[2,0],[1,.8]],[1.],protect_setup=True,local_refinement=True)
        self.assertEqual(joint,origin);self.assertFalse(evidence['converged'])
        self.assertEqual(evidence['refinement']['status'],'local_patch_unavailable')
