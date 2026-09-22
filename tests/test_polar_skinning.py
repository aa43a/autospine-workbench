import unittest
import numpy as np
from autospine_workbench.targets.character43.polar_skinning import solve


class PolarSkinningTests(unittest.TestCase):
    bones=[{'name':'a'},{'name':'b'}]
    setup={'a':(1,0,0,1,0,0),'b':(1,0,0,1,0,0)}

    def test_bind_pose_and_single_bone_are_exact(self):
        points=[[2,3],[4,5]];weights=[[(0,.3),(1,.7)],[(1,1)]]
        result,_=solve(points,weights,self.bones,self.setup,self.setup)
        np.testing.assert_allclose(result,points)
        current=dict(self.setup,b=(0,-1,.5,0,10,20))
        result,_=solve([[4,5]],[[(1,1)]],self.bones,self.setup,current)
        np.testing.assert_allclose(result,[[5,22]])

    def test_shared_pivot_rotation_does_not_collapse_mid_blend(self):
        current=dict(self.setup,b=(0,-1,1,0,0,0))
        result,report=solve([[1,0]],[[(0,.5),(1,.5)]],self.bones,self.setup,current)
        self.assertAlmostEqual(np.linalg.norm(result[0]),1)
        np.testing.assert_allclose(result[0],[2**-.5,2**-.5])
        self.assertFalse(report['selected'])

    def test_antipodal_rotation_rejected(self):
        with self.assertRaisesRegex(ValueError,'rotation_ambiguous'):
            solve([[1,0]],[[(0,.5),(1,.5)]],self.bones,self.setup,dict(self.setup,b=(-1,0,0,-1,0,0)))

    def test_shared_joint_preserves_hinge_position(self):
        bones=[{'name':'a'},{'name':'b','parent':'a'}]
        setup=dict(self.setup,b=(1,0,0,1,1,0))
        current=dict(setup,b=(0,-1,1,0,1,0))
        result,_=solve([[1,0]],[[(0,.5),(1,.5)]],bones,setup,current,shared_joint=True)
        np.testing.assert_allclose(result,[[1,0]])

    def test_shared_joint_requires_known_chain(self):
        with self.assertRaisesRegex(ValueError,'unrelated_bones'):
            solve([[1,0]],[[(0,.5),(1,.5)]],self.bones,self.setup,self.setup,shared_joint=True)

    def test_invalid_weights_and_reflection_rejected(self):
        with self.assertRaisesRegex(ValueError,'weights_invalid'):
            solve([[1,0]],[[(0,.4)]],self.bones,self.setup,self.setup)
        with self.assertRaisesRegex(ValueError,'orientation_invalid'):
            solve([[1,0]],[[(0,1)]],self.bones,self.setup,dict(self.setup,a=(-1,0,0,1,0,0)))
