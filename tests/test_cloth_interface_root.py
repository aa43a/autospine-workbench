import unittest
from autospine_workbench.asset.planning.cloth_interface_root import interface


class InterfaceRootTests(unittest.TestCase):
    def test_shared_semantic_edge_root_and_scale_translation(self):
        points=[[0.,0.],[4.,0.],[0.,2.],[4.,2.]];tri=[[0,1,2],[1,3,2]]
        roles=[dict(role='hanging_cloth'),dict(role='cuff')]
        result=interface(points,tri,roles)
        self.assertEqual(result['edges'],[[1,2]]);self.assertEqual(result['root_xy'],[2.,1.])
        self.assertEqual(result['connected_components'],1)
        changed=interface([[100-3*x,50+3*y] for x,y in points],tri,roles)
        self.assertEqual(changed['root_xy'],[94.,53.]);self.assertAlmostEqual(changed['total_length'],3*result['total_length'])

    def test_unknown_and_hand_do_not_define_clothing_root(self):
        p=[[0.,0.],[4.,0.],[0.,2.],[4.,2.]];tri=[[0,1,2],[1,3,2]]
        for role in ['unknown','hand','hanging_cloth']:
            r=interface(p,tri,[dict(role='hanging_cloth'),dict(role=role)])
            self.assertIsNone(r['root_xy']);self.assertEqual(r['reason_code'],'ambiguous_or_missing_interface')
        with self.assertRaises(ValueError):interface(p,tri,[])

    def test_disconnected_interfaces_are_not_silently_merged(self):
        p=[[0.,0.],[4.,0.],[0.,2.],[4.,2.],[10.,0.],[14.,0.],[10.,2.],[14.,2.]]
        r=interface(p,[[0,1,2],[1,3,2],[4,5,6],[5,7,6]],[dict(role=x) for x in ['hanging_cloth','sleeve']*2])
        self.assertEqual(r['connected_components'],2);self.assertEqual(r['reason_code'],'ambiguous_or_missing_interface')
