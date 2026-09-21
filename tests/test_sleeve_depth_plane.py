import math
import unittest

from autospine_workbench.targets.character43.sleeve_depth_plane import fit,at


class SleeveDepthPlaneTests(unittest.TestCase):
    def test_anchors_mirroring_scale_and_vertical_invariance(self):
        for sign in (-1,1):
            for scale in (.1,1,10):
                a=[10,20];b=[10+sign*30*scale,20-40*scale]
                result=fit(a,b,[-.2,.3]);dx,dy,offset=result['coefficients']
                self.assertAlmostEqual(dx*a[0]+dy*a[1]+offset,-.2)
                self.assertAlmostEqual(dx*b[0]+dy*b[1]+offset,.3)
                self.assertAlmostEqual(dx*b[0]+dy*(b[1]-1000)+offset,.3)
                self.assertFalse(result['selected'])

    def test_degenerate_or_nonfinite_does_not_invent_plane(self):
        for b in ([0,0],[0,100],[1,100]):
            with self.assertRaisesRegex(ValueError,'degenerate'):fit([0,0],b,[0,.1])
        with self.assertRaisesRegex(ValueError,'nonfinite'):fit([0,0],[math.nan,1],[0,.1])

    def test_explicit_helper_binding_and_current_wrist_are_required(self):
        document=dict(bones=[dict(name='forearm_l',x=0,y=0,rotation=0,length=10),
            dict(name='hand_l',parent='forearm_l',x=10,y=0,rotation=0),
            dict(name='cloth',parent='forearm_l',x=10,y=0,rotation=-60)],animations={'test':{}})
        sampler=lambda _:dict(forearm_l=(0,.2))
        result=at(document,'test',0,sampler,0,'cloth','forearm_l')
        self.assertEqual(result['anchors']['wrist']['depth'],.2)
        document['animations']['test']={'bones':{'cloth':{'translate':[dict(time=0,x=1,y=0)]}}}
        with self.assertRaisesRegex(ValueError,'detached'):at(document,'test',0,sampler,0,'cloth','forearm_l')
        document['animations']['test']={};document['bones'][2]['parent']='hand_l'
        with self.assertRaisesRegex(ValueError,'binding'):at(document,'test',0,sampler,0,'cloth','forearm_l')

    def test_missing_source_and_wrong_helper_root_rejected(self):
        document=dict(bones=[dict(name='forearm_r',x=0,y=0,rotation=0,length=10),
            dict(name='hand_r',parent='forearm_r',x=10,y=0,rotation=0),
            dict(name='cloth',parent='forearm_r',x=10,y=0,rotation=0)],animations={'test':{}})
        with self.assertRaisesRegex(ValueError,'source_depth'):at(document,'test',0,lambda _: {},0,'cloth','forearm_r')
        document['bones'][2]['x']=9
        with self.assertRaisesRegex(ValueError,'wrist_attachment'):at(document,'test',0,lambda _: {},0,'cloth','forearm_r')


if __name__=='__main__':unittest.main()
