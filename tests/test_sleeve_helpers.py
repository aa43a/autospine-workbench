from copy import deepcopy
import math
import unittest
from autospine_workbench.asset.planning.sleeve_helpers import frames,make_helper
from autospine_workbench.asset.joints.mesh_weights import _deform


class SleeveHelperTests(unittest.TestCase):
    def fixture(self):
        bones=[dict(id='upper',parent_id='chest',head_xy=[0.,0.],tail_xy=[10.,0.],world_rotation_degrees=0.),
               dict(id='forearm',parent_id='upper',head_xy=[10.,0.],tail_xy=[20.,0.],world_rotation_degrees=0.),
               dict(id='hand',parent_id='forearm',head_xy=[20.,0.],tail_xy=[25.,0.],world_rotation_degrees=0.)]
        points=[[18.,5.],[20.,8.],[24.,8.]]
        mesh=dict(vertices_xy=points,weights=[[dict(bone_id=b['id'],weight=w,local_xy=[p[0]-b['head_xy'][0],p[1]])
                  for b,w in zip(bones,[0.,.5,.5])] for p in points])
        return mesh,bones

    def test_sibling_fk_and_setup_reconstruction(self):
        mesh,bones=self.fixture();original=deepcopy(mesh)
        helper,weights,vertices=make_helper(mesh,bones,[['hanging_cloth']]*3,'cloth')
        chain=bones+[helper];rest=_deform(weights,frames(chain,{}));hand=_deform(weights,frames(chain,{'hand':90}))
        self.assertEqual(rest,hand);self.assertEqual(mesh,original)
        for a,b in zip(rest,mesh['vertices_xy']):self.assertLess(math.dist(a,b),1e-9)
        moved=_deform(weights,frames(chain,{'cloth':15}))
        self.assertTrue(any(math.dist(a,b)>1 for a,b in zip(rest,moved)))
        parent=frames(chain,{'forearm':90})
        for actual,expected in zip(parent['cloth'][0],[10.,10.]):self.assertAlmostEqual(actual,expected)
        self.assertEqual(helper['parent_id'],'forearm')
        self.assertTrue(all(abs(sum(w['weight'] for w in row)-1)<1e-9 for row in weights))

    def test_mixed_vertices_preserved_and_invalid_hierarchy_rejected(self):
        mesh,bones=self.fixture();helper,weights,vertices=make_helper(mesh,bones,[['hanging_cloth'],['hand','hanging_cloth'],['unknown']],'cloth')
        self.assertEqual(vertices,[0]);self.assertEqual(weights[1:],mesh['weights'][1:])
        self.assertIsNone(make_helper(mesh,bones,[['unknown']]*3,'cloth'))
        with self.assertRaises(ValueError):frames([helper]+bones,{})
        with self.assertRaises(ValueError):frames(bones,{'missing':10})
        with self.assertRaises(ValueError):frames(bones,{'hand':float('nan')})
