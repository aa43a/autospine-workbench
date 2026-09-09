from copy import deepcopy
import unittest
from autospine_workbench.asset.planning.sleeve_boundary import reweight


class SleeveBoundaryTests(unittest.TestCase):
    def fixture(self):
        bones=['upperarm_l','forearm_l','hand_l']
        return dict(vertices_xy=[[i,i%2] for i in range(6)],triangles=[[0,1,2],[1,2,3],[2,3,4],[3,4,5]],bone_ids=bones,
            weights=[[dict(bone_id=b,weight=w,local_xy=[i,0]) for b,w in zip(bones,[.2,.3,.5])] for i in range(6)]),[
                dict(role=r) for r in ['hanging_cloth','cuff','cuff','hand']]

    def test_pinned_hand_and_garment_with_bounded_transition(self):
        mesh,roles=self.fixture();old=deepcopy(mesh);result,info=reweight(mesh,roles)
        self.assertEqual(mesh,old);self.assertEqual((result,info),reweight(mesh,roles))
        self.assertEqual(info['hand_retention'][0],0.)
        for i in [3,4,5]:self.assertEqual(result['weights'][i],mesh['weights'][i])
        for i in [1,2]:self.assertGreater(info['hand_retention'][i],0);self.assertLess(info['hand_retention'][i],1)
        for a,b in zip(mesh['weights'],result['weights']):
            self.assertEqual(a[0],b[0]);self.assertAlmostEqual(sum(w['weight'] for w in b),1.)
            self.assertEqual([w['local_xy'] for w in a],[w['local_xy'] for w in b])
        self.assertEqual(mesh['triangles'],result['triangles'])

    def test_unknown_pinned_scale_independent_and_no_anchors_noop(self):
        mesh,roles=self.fixture();roles[-1]['role']='unknown'
        result,info=reweight(mesh,roles)
        for i in [3,4,5]:self.assertEqual(result['weights'][i],mesh['weights'][i])
        moved=deepcopy(mesh);moved['vertices_xy']=[[300-5*x,100+5*y] for x,y in mesh['vertices_xy']]
        self.assertEqual(info,reweight(moved,roles)[1])
        self.assertEqual(reweight(mesh,[dict(role='cuff')]*4)[0],mesh)
        with self.assertRaises(ValueError):reweight(mesh,roles[:-1])
