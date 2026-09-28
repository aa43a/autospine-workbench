import unittest
from autospine_workbench.depth_order_schmitt import evaluate_depth_pair

class TimeHoldTests(unittest.TestCase):
    def evaluate(self,times):
        rows=[dict(tick=t,source_frame_index=i,scores=dict(arm=1,body=0)) for i,t in enumerate(times)]
        return evaluate_depth_pair(rows,slot_ids=('arm','body'),setup_front_slot='body',
            enter_threshold=.04,exit_threshold=.02,minimum_hold_frames=1,minimum_hold_ticks=66667)
    def test_dense_interpolation_cannot_shorten_elapsed_hold(self):
        sparse=self.evaluate([0,33333,66667,100000])[1]
        dense=self.evaluate([0,100,200,1000,2000,33333,66667,100000])[1]
        self.assertEqual([e['tick'] for e in sparse],[66667]);self.assertEqual([e['tick'] for e in dense],[66667])
        self.assertEqual(self.evaluate([0,1,2,3,4,5])[1],[])
    def test_time_order_and_type_rejected(self):
        for times in ([0,2,1],[0,0],[0,True]):
            with self.assertRaises(ValueError):self.evaluate(times)
