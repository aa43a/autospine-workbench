import unittest
from m4_reach_held_order import evidence
from autospine_workbench.targets.character43.depth_interval_evidence import requests,IntervalEvidenceError


class ReachHeldOrderTests(unittest.TestCase):
    def test_uncertainty_is_not_converted_to_default_approval(self):
        for status in ('unmeasured','requires_partition_or_more_depth'):
            row=evidence(dict(status=status),10,20,'arm','body','body')
            self.assertTrue(row['ambiguous'])
            self.assertEqual(row['current_front_slot'],'body')
            self.assertEqual(row['source_tick'],20)

    def test_only_uniform_proxy_changes_requested_front(self):
        for status,front in [('uniform_front_proxy','arm'),('uniform_back_proxy','body')]:
            row=evidence(dict(status=status),10,20,'arm','body','body')
            self.assertFalse(row['ambiguous'])
            self.assertEqual(row['current_front_slot'],front)

    def test_visible_midpoint_direction_conflict_blocks(self):
        class Probe:
            def pair(self,a,b,time):return dict(overlap_pixels=1,roi=[0,0,1,1])
        row=evidence(dict(status='uniform_front_proxy'),0,0,'arm','body','body')
        row['interval_sample']=evidence(dict(status='uniform_back_proxy'),500000,500000,'arm','body','body')
        with self.assertRaisesRegex(IntervalEvidenceError,'visible_depth_order_changes_within_interval'):
            requests(dict(arm_slot='arm',torso_slot='body'),row,[0,.5],Probe(),strict=True)
