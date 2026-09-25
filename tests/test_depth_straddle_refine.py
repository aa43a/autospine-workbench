from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from autospine_workbench.targets.character43.depth_straddle_refine import refine


class RefinementTests(unittest.TestCase):
    def test_explicit_baked_plane_survives_per_pair_checker_recreation(self):
        provider=Mock()
        depth=dict(pairs=[dict(arm_slot=a,torso_slot=b,samples=[dict(tick=0,source_tick=0,
            ambiguous=True,current_front_slot=a)]) for a,b in [('a','b'),('c','d')]])
        checker=Mock();checker.axes={}
        checker.check.return_value=dict(status='uniform_front_proxy')
        with patch('autospine_workbench.targets.character43.torso_depth_refinement.Checker',return_value=checker) as factory:
            _,report=refine({'slots':[]},{},'test',depth,None,torso_plane=True,pair_budgets=True,plane_provider=provider)
        self.assertEqual(report['resolved_rows'],2)
        self.assertEqual(len(factory.call_args_list),3)
        self.assertTrue(all(call.kwargs['plane_provider'] is provider for call in factory.call_args_list))
        self.assertEqual(report['torso_plane_source'],'explicit_provider_not_unwarped_bones')
        with self.assertRaisesRegex(ValueError,'requires_torso_model'):
            refine({}, {},'test',depth,None,plane_provider=provider)

    def test_pair_budgets_do_not_starve_later_pairs(self):
        depth=dict(pairs=[dict(arm_slot=a,torso_slot=b,samples=[dict(tick=0,source_tick=0,
            ambiguous=True,current_front_slot=a)]) for a,b in [('a','b'),('c','d')]])
        def measure(probe,*args,**kwargs):
            if probe.remaining<40_000_000: raise ValueError('depth_overlap_pixel_budget')
            probe.remaining-=40_000_000
            return dict(status='uniform_front_proxy')
        module='autospine_workbench.targets.character43.depth_straddle_refine.'
        with patch(module+'Probe',side_effect=lambda *a,**k:SimpleNamespace(remaining=64_000_000)), \
             patch(module+'overlap_support',side_effect=measure):
            _,legacy=refine({}, {},'test',depth,lambda t:{})
            _,per_pair=refine({}, {},'test',depth,lambda t:{},pair_budgets=True)
        self.assertEqual(legacy['resolved_rows'],1)
        self.assertEqual(per_pair['resolved_rows'],2)
        self.assertEqual(per_pair['pixel_budget_used'],80_000_000)
        self.assertTrue(all(r['pixel_budget_used']==40_000_000 for r in per_pair['pair_budgets']))
        with self.assertRaisesRegex(ValueError,'pair_resource_limit'):
            refine({'slots':[]},{},'test',dict(pairs=depth['pairs']*9),None,pair_budgets=True)

    def test_refinement_passes_only_completed_overlap_to_order_probe(self):
        from test_motion_depth_overlap import fixture
        from autospine_workbench.targets.character43.motion_depth_overlap import Probe
        doc,files=fixture(); doc['bones'][0]['length']=2
        depth=dict(pairs=[dict(arm_slot='a',torso_slot='b',samples=[
            dict(tick=0,source_tick=0,ambiguous=True,current_front_slot='a')])])
        target=Probe(doc,files,'test')
        candidate,report=refine(doc,files,'test',depth,lambda tick:{'root':(.1,.2)},order_probe=target)
        self.assertEqual(report['reused_order_overlap_samples'],1)
        self.assertEqual(target.pair('a','b',0)['overlap_pixels'],4)
        self.assertEqual(target.remaining,64_000_000)
        self.assertFalse(candidate['pairs'][0]['samples'][0]['ambiguous'])

    def test_plane_mode_keeps_held_order_and_checks_source_midpoint(self):
        depth=dict(pairs=[dict(arm_slot='a',torso_slot='b',samples=[
            dict(tick=0,source_tick=200000,ambiguous=True,current_front_slot='b'),
            dict(tick=100000,source_tick=300000,ambiguous=False,current_front_slot='b')])])
        checker=Mock(); checker.axes={}
        checker.check.side_effect=[dict(status='uniform_front_proxy'),dict(status='uniform_front_proxy')]
        with patch('autospine_workbench.targets.character43.torso_depth_refinement.Checker',return_value=checker):
            candidate,report=refine({'slots':[]}, {},'test',depth,None,torso_plane=True)
        self.assertTrue(candidate['pairs'][0]['samples'][0]['ambiguous'])
        self.assertEqual(candidate['pairs'][0]['samples'][0]['current_front_slot'],'b')
        self.assertEqual([c.args[-1] for c in checker.check.call_args_list],[200000,250000])
        self.assertEqual(report['resolved_rows'],0)
        self.assertIn('planar_torso',report['assumptions'])

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
