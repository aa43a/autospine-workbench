from copy import deepcopy
import unittest
from autospine_workbench.asset.planning.sleeve_weights import reweight


class SleeveWeightTests(unittest.TestCase):
    def test_roles_boundaries_and_weight_invariants(self):
        roles=['sleeve','hanging_cloth','hand','cuff','unknown']
        triangles=[[3*i,3*i+1,3*i+2] for i in range(5)]+[[0,3,6]]
        mesh=dict(vertices_xy=[[float(i),0.] for i in range(15)],triangles=triangles,
                  bone_ids=['upperarm_l','forearm_l','hand_l'],weights=[[
                      dict(bone_id=b,weight=w,local_xy=[i,1.]) for b,w in zip(['upperarm_l','forearm_l','hand_l'],[.2,.3,.5])] for i in range(15)])
        assignments=[dict(role=r) for r in roles+['unknown']];original=deepcopy(mesh)
        result,info=reweight(mesh,assignments)
        self.assertEqual(info['changed_vertices'],[1,2,4,5])
        self.assertEqual(info['mixed_boundary_vertices'],[0,3,6])
        self.assertEqual(info['changed_role_counts'],{'sleeve':2,'hanging_cloth':2})
        self.assertEqual(mesh,original);self.assertEqual(result['triangles'],mesh['triangles'])
        for i,(a,b) in enumerate(zip(mesh['weights'],result['weights'])):
            self.assertAlmostEqual(sum(w['weight'] for w in b),1.)
            self.assertEqual(a[0],b[0])
            self.assertEqual([w['local_xy'] for w in a],[w['local_xy'] for w in b])
            if i not in info['changed_vertices']:self.assertEqual(a,b)
            else:self.assertEqual([w['weight'] for w in b],[.2,.8,0.])
        self.assertEqual((result,info),reweight(mesh,assignments))
        with self.assertRaises(ValueError):reweight(mesh,assignments[:-1])

    def test_already_separated_sleeve_is_noop(self):
        mesh=dict(vertices_xy=[[0,0],[1,0],[0,1]],triangles=[[0,1,2]],bone_ids=['a','b','c'],
                  weights=[[dict(bone_id=b,weight=w,local_xy=[0,0]) for b,w in zip(['a','b','c'],[.2,.8,0.])] for _ in range(3)])
        result,info=reweight(mesh,[dict(role='sleeve')])
        self.assertEqual(result,mesh);self.assertEqual(info['changed_vertices'],[])
