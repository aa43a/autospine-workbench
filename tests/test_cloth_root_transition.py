from copy import deepcopy
import unittest
from autospine_workbench.asset.planning.cloth_root_transition import reweight


class ClothRootTransitionTests(unittest.TestCase):
    def fixture(self):
        chain=[dict(id='upper',head_xy=[-10.,0.],tail_xy=[0.,0.],world_rotation_degrees=0.),
               dict(id='forearm',head_xy=[0.,0.],tail_xy=[10.,0.],world_rotation_degrees=0.),
               dict(id='hand',head_xy=[10.,0.],tail_xy=[12.,0.],world_rotation_degrees=0.)]
        points=[[0.,0.],[0.,1.],[1.,0.],[1.,1.],[3.,0.],[3.,1.]]
        mesh=dict(vertices_xy=points,triangles=[[0,1,2],[1,2,3],[2,3,4],[3,4,5]],weights=[[
            dict(bone_id=b['id'],weight=w,local_xy=[p[0]-b['head_xy'][0],p[1]]) for b,w in zip(chain,[.2,.8,0.])] for p in points])
        helper=dict(id='cloth',head_xy=[10.,0.],world_rotation_degrees=0.)
        return mesh,chain,helper,[2,3,4,5]

    def test_distance_gradient_fixed_boundary_and_replay(self):
        args=self.fixture();original=deepcopy(args);weights,info=reweight(*args)
        self.assertEqual(args,original);self.assertEqual((weights,info),reweight(*args))
        self.assertEqual(weights[:2],args[0]['weights'][:2]);self.assertEqual(info['unreachable_vertices'],[])
        self.assertGreater(info['helper_factors']['2'],0);self.assertLess(info['helper_factors']['2'],1)
        self.assertEqual(info['helper_factors']['4'],1)
        for row in weights:self.assertAlmostEqual(sum(w['weight'] for w in row),1.)
        self.assertEqual([r[0] for r in weights],[r[0] for r in args[0]['weights']])

    def test_scale_invariance_and_disconnected_root(self):
        args=self.fixture();expected=reweight(*args)[1]['helper_factors']
        changed=deepcopy(args)
        changed[0]['vertices_xy']=[[30-4*x,20+4*y] for x,y in changed[0]['vertices_xy']]
        for b in changed[1]:
            for k in ['head_xy','tail_xy']:b[k]=[30-4*b[k][0],20+4*b[k][1]]
        self.assertEqual(reweight(*changed)[1]['helper_factors'],expected)
        args[-1][:]=list(range(6))
        weights,info=reweight(*args)
        self.assertEqual(info['unreachable_vertices'],list(range(6)))
        self.assertEqual(weights,args[0]['weights'])
