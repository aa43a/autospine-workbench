from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.transverse_gain_feasibility import screen


def pose(reverse=False):
    a=[[0.,0.],[1.,0.],[0.,1.]];b=[[0.,0.],[1.,0.],[0.,.1]]
    return dict(time=int(reverse),zero=b if reverse else a,one=a if reverse else b,
                floors=[.5],context=dict(row={'triangles':[[0,1,2]]},areas=[.5],
                                        budget=.1,free=[False]*3))


class GainScreenTests(unittest.TestCase):
    def test_actual_world_surface_is_affine_in_gain_at_exact_pose(self):
        from test_limb_transverse_repair import fixture
        from autospine_workbench.targets.character43.limb_transverse_repair import build
        from autospine_workbench.targets.character43.affine_pose import sample
        doc=fixture();time=.371
        doc['animations']['motion']['attachments']={'default':{'leg':{'leg':{'deform':[
            dict(time=0,vertices=[0.]*6),dict(time=1,vertices=[1.,2.,-2.,4.,3.,-1.])]}}}}
        def points(gain):
            candidate,_=build(doc,'motion',['leg'],correction_frame='transverse',
                              anchor_terminal=True,required_times=[time],distal_gain=gain)
            return sample(candidate,'motion',time)[0]['leg']
        zero,one=points(0.),points(1.)
        for gain in (.0625,.25,.5):
            for a,b,p in zip(zero,one,points(gain)):
                for k in (0,1):self.assertAlmostEqual(p[k],a[k]+gain*(b[k]-a[k]),places=9)

    def test_requires_one_gain_across_all_poses_not_individual_choices(self):
        result=screen([pose(),pose(True)],[0.,1.])
        self.assertEqual(result['unexcluded_gains'],[])
        self.assertIsNone(result['suggested_gain'])
        self.assertEqual([len(r['failures']) for r in result['trials']],[1,1])

    def test_unexcluded_gain_is_not_acceptance(self):
        poses=[pose(),pose(True)];before=deepcopy(poses)
        result=screen(poses,[0.,.5,1.])
        self.assertEqual(result['unexcluded_gains'],[.5])
        self.assertEqual(result['suggested_gain'],.5)
        self.assertFalse(result['selected']);self.assertFalse(result['production_authorized'])
        self.assertEqual(poses,before)

    def test_rejects_nonfinite_missing_duplicate_and_bad_inventory(self):
        for gains in ([],[0,0],[float('nan')],[1.1]):
            with self.assertRaises(ValueError):screen([pose()],gains)
        p=pose();p['one'].pop()
        with self.assertRaises(ValueError):screen([p],[0.])
