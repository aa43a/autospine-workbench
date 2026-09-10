import math
import unittest
from copy import deepcopy
from autospine_workbench.asset.planning.sleeve_hand_rigidity import reweight
from autospine_workbench.asset.joints.mesh_weights import _deform,_area


class HandRigidityTests(unittest.TestCase):
    def test_owned_hand_is_rigid_and_setup_is_preserved(self):
        p=[[1.,1.],[3.,1.],[1.,3.]];w=[[dict(bone_id='forearm',weight=1.,local_xy=x[:])] for x in p]
        hand=dict(id='hand',head_xy=[1.,1.],world_rotation_degrees=45.)
        result,selected=reweight(p,w,[[0,1,2]],[dict(role='hand')],hand)
        self.assertEqual(selected,[0,1,2])
        rest=_deform(result,{'hand':([1.,1.],45.)});moved=_deform(result,{'hand':([1.,1.],75.)})
        for a,b in zip(rest,p):self.assertLess(math.dist(a,b),1e-10)
        self.assertAlmostEqual(_area(moved,[0,1,2]),_area(p,[0,1,2]))
        self.assertTrue(all(e[0]['bone_id']=='forearm' for e in w))

    def test_shared_unknown_and_nonhand_are_unchanged(self):
        p=[[0.,0.],[2.,0.],[0.,2.],[2.,2.]];w=[[dict(bone_id='a',weight=1.,local_xy=x[:])] for x in p]
        hand=dict(id='hand',head_xy=[0.,0.],world_rotation_degrees=0.)
        result,selected=reweight(p,w,[[0,1,2],[1,3,2]],[dict(role='hand'),dict(role='unknown')],hand)
        self.assertEqual(selected,[0]);self.assertEqual(result[1:],w[1:])
