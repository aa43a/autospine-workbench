from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.depth_straddle_refine import refine


class RefinementTests(unittest.TestCase):
    def run_case(self,statuses):
        depth=dict(pairs=[dict(arm_slot='a',torso_slot='b',samples=[
            dict(tick=0,source_tick=200000,ambiguous=True,current_front_slot='b'),
            dict(tick=100000,source_tick=300000,ambiguous=False,current_front_slot='b')])])
        original=deepcopy(depth); calls=[]
        with patch('autospine_workbench.targets.character43.depth_straddle_refine.Probe',return_value=SimpleNamespace(remaining=123)), \
             patch('autospine_workbench.targets.character43.depth_straddle_refine.overlap_support',
                   side_effect=[dict(status=s) for s in statuses]):
            candidate,report=refine({}, {},'test',depth,lambda tick:calls.append(tick) or {})
        self.assertEqual(depth,original)
        self.assertEqual(calls,[200000,250000])
        return candidate,report

    def test_both_frame_and_midpoint_must_support_held_order(self):
        _,report=self.run_case(['uniform_back_proxy','uniform_back_proxy'])
        self.assertEqual(report['resolved_rows'],1)
        self.assertFalse(report['selected'])
        for states in [('uniform_back_proxy','requires_partition_or_more_depth'),
                       ('uniform_front_proxy','uniform_front_proxy'),('no_overlap','no_overlap')]:
            candidate,report=self.run_case(states)
            self.assertEqual(report['resolved_rows'],0)
            self.assertTrue(candidate['pairs'][0]['samples'][0]['ambiguous'])

    def test_midpoint_can_be_visible_even_if_source_frame_is_not(self):
        _,report=self.run_case(['no_overlap','uniform_back_proxy'])
        self.assertEqual(report['resolved_rows'],1)


if __name__=='__main__':unittest.main()
