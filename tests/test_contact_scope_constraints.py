import unittest
from autospine_workbench.targets.character43.contact_scope_constraints import inspect


class ContactConstraintsTests(unittest.TestCase):
    def setUp(self):
        self.rest=[[0,0],[2,0],[2,2],[0,2]];self.flat=[0,1,2,0,2,3]

    def check(self,regions,reference=None):
        return inspect(self.rest,self.rest,self.flat,self.rest,reference or self.rest,self.flat,regions)

    def test_unknown_shared_vertex_cannot_be_silently_moved(self):
        result=self.check(dict(fixed=[0],sliding=[],free=[]),[[3,0],[5,0],[5,2],[3,2]])
        self.assertEqual([r['vertex'] for r in result['conflicts']],[0,2])
        self.assertEqual(result['unknown_triangles'],[1])
        self.assertTrue(all(r['required_displacement_px']==3 for r in result['conflicts']))
        self.assertFalse(result['sufficient_for_repair'])

    def test_shared_topology_alone_is_not_a_motion_conflict(self):
        result=self.check(dict(fixed=[0],sliding=[],free=[1]))
        self.assertEqual(result['shared_preserved_vertices'],[0,2])
        self.assertEqual(result['conflicts'],[])
        self.assertEqual(result['status'],'no_local_counterexample')
        self.assertFalse(result['sufficient_for_repair'])

    def test_sliding_never_treated_as_supported_fixed_constraints(self):
        result=self.check(dict(fixed=[],sliding=[0],free=[1]))
        self.assertIn('sliding_constraints_not_implemented',result['reasons'])
        self.assertEqual(result['fixed_targets'],[])

    def test_outside_reference_and_overlapping_labels_rejected(self):
        result=inspect(self.rest,self.rest,self.flat,[[10,10],[11,10],[10,11]],
                       [[10,10],[11,10],[10,11]],[0,1,2],dict(fixed=[0],sliding=[],free=[]))
        self.assertEqual(result['unsupported_vertices'],[0,1,2])
        with self.assertRaises(ValueError):self.check(dict(fixed=[0],sliding=[0],free=[]))

    def test_explicit_transition_releases_unknown_but_does_not_claim_repair(self):
        result=self.check(dict(fixed=[0],sliding=[],free=[],transition=[1]),
                          [[3,0],[5,0],[5,2],[3,2]])
        self.assertEqual(result['conflicts'],[])
        self.assertEqual(result['unknown_triangles'],[])
        self.assertEqual(result['transition_only_vertices'],[3])
        self.assertIn('transition_constraints_not_implemented',result['reasons'])
        self.assertFalse(result['sufficient_for_repair'])

    def test_transition_boundary_does_not_override_preserved_region(self):
        result=self.check(dict(fixed=[],sliding=[],free=[0],transition=[1]))
        self.assertEqual(result['transition_preserved_vertices'],[0,2])
        self.assertEqual(result['transition_only_vertices'],[3])

    def test_covering_reference_can_slide_away_without_a_fixed_target(self):
        result=self.check(dict(fixed=[],sliding=[],free=[],occlusion=[0,1]),
                          [[30,0],[32,0],[32,2],[30,2]])
        self.assertEqual(result['fixed_targets'],[])
        self.assertEqual(result['conflicts'],[])
        self.assertEqual(result['vertex_roles']['occlusion'],[0,1,2,3])
        self.assertEqual(result['occlusion_review']['status'],'rendered_overlap_not_checked')
        self.assertTrue(result['occlusion_review']['required'])
        self.assertFalse(result['sufficient_for_repair'])

    def test_covering_region_preserves_shared_vertices_against_fixed_motion(self):
        result=self.check(dict(fixed=[0],sliding=[],free=[],occlusion=[1]),
                          [[3,0],[5,0],[5,2],[3,2]])
        self.assertEqual([r['vertex'] for r in result['conflicts']],[0,2])
        self.assertTrue(all(r['preserved_by']==['occlusion'] for r in result['conflicts']))
        with self.assertRaises(ValueError):
            self.check(dict(fixed=[0],sliding=[],free=[],occlusion=[0]))
