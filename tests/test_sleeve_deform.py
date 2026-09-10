import math
import unittest
from autospine_workbench.targets.spine43.sleeve_deform import local_offsets,offset_at,compile_region
from autospine_workbench.asset.joints.mesh_weights import _rotate


class SleeveDeformTests(unittest.TestCase):
    def test_weighted_local_offsets_reconstruct_world_delta(self):
        weights=[[dict(bone_id='a',weight=.3),dict(bone_id='b',weight=.7)]]
        frames={'a':([20.,40.],75.),'b':([-5.,10.],-42.)};delta=[[3.,-7.]]
        values=local_offsets(weights,delta,frames);actual=[0.,0.]
        for i,e in enumerate(weights[0]):
            p=_rotate([values[2*i],-values[2*i+1]],frames[e['bone_id']][1])
            for k in (0,1):actual[k]+=e['weight']*p[k]
        self.assertLess(math.dist(actual,delta[0]),1e-12)

    def test_unselected_correction_and_fractional_interpolation(self):
        track=dict(correction_selected=False,trial_keys=[[[float(i),0.]] for i in range(33)])
        self.assertEqual(offset_at(track,3.5,1),[[0.,0.]])
        track['correction_selected']=True
        self.assertEqual(offset_at(track,3.5,1),[[.875,0.]])
        self.assertEqual(offset_at(track,128,1),[[32.,0.]])
        with self.assertRaises(ValueError):compile_region({}, {}, {}, {})
