import unittest
from m4_reach_partial_order import pair_samples
from autospine_workbench.targets.character43.motion_depth_order import build


class PartialOrderTests(unittest.TestCase):
    def test_unknown_midpoint_retained_not_approved(self):
        samples,unknown=pair_samples(dict(slot='arm',body='chest'),'FAF',[{'tick':0},{'tick':100}])
        self.assertEqual([s['tick'] for s in samples],[100])
        self.assertEqual(unknown,[dict(slot='arm',tick=0,states='FA')])

    def test_scheduled_unconstrained_frame_restores_setup(self):
        class Probe:
            def pair(self,a,b,time):return dict(overlap_pixels=1)
        document=dict(slots=[{'name':'arm'},{'name':'body'}],animations={'test':{}})
        depth=dict(pairs=[dict(arm_slot='arm',torso_slot='body',samples=[
            dict(tick=0,ambiguous=False,current_front_slot='arm')])])
        candidate,report=build(document,'test',depth,Probe(),evaluation_ticks=[0,100])
        self.assertIsNotNone(candidate)
        self.assertEqual(report['frames'][-1]['order'],['arm','body'])
        with self.assertRaises(ValueError):build(document,'test',depth,Probe(),evaluation_ticks=[100])
