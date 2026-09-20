from copy import deepcopy
import unittest
from unittest.mock import patch
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.cloth_depth_constraints import build, held_front
from autospine_workbench.targets.character43.motion_depth_overlap import Probe

MODULE='autospine_workbench.targets.character43.cloth_depth_constraints.'


class ClothConstraintsTests(unittest.TestCase):
    def test_midpoint_disagreement_and_unmeasured_are_ambiguous(self):
        front=dict(status='uniform_front_proxy'); back=dict(status='uniform_back_proxy')
        for checks in ([front,back],[front,dict(status='unmeasured')], [front,dict(status='requires_partition_or_more_depth')]):
            self.assertEqual(held_front(checks,'arm','cloth','cloth'),('cloth',True))
        self.assertEqual(held_front([front,dict(status='no_overlap')],'arm','cloth','cloth'),('arm',False))
        self.assertEqual(held_front([dict(status='no_overlap')],'arm','cloth','cloth'),('cloth',False))

    def test_complete_source_ticks_and_midpoints_preserve_original(self):
        doc,files=fixture(); doc['bones'][0]['length']=2
        depth=dict(groups={'left':['a'],'right':[]},pairs=[dict(samples=[
            dict(tick=t,source_tick=t+200000,ambiguous=False) for t in (0,100000)])])
        original=deepcopy(depth); partition=dict(regions=[dict(slot='b',group='mixed')])
        observed=[]
        order_probe=Probe(doc,files,'test')
        def source(tick): observed.append(tick); return {'root':(.1,.2)}
        with patch(MODULE+'at',return_value={'coefficients':[0,0,0]}), patch(MODULE+'observe',return_value={'segments':{}}):
            result,report=build(doc,files,'test',depth,partition,source,order_probe=order_probe)
        self.assertEqual(observed,[200000,250000,300000])
        self.assertEqual(report['unmeasured_samples'],0)
        self.assertEqual([r['current_front_slot'] for r in result['pairs'][-1]['samples']],['a','a'])
        self.assertEqual(depth,original)
        self.assertFalse(report['selected'])
        self.assertEqual(report['reused_order_overlap_samples'],3)
        self.assertEqual(order_probe.pair('a','b',.05)['overlap_pixels'],4)
        self.assertEqual(order_probe.remaining,64_000_000)
        with self.assertRaisesRegex(ValueError,'probe_identity'):
            build(deepcopy(doc),files,'test',depth,partition,source,order_probe=order_probe)

    def test_resource_failure_remains_explicit(self):
        doc,files=fixture(); depth=dict(groups={'left':['a'],'right':[]},pairs=[
            dict(samples=[dict(tick=0,source_tick=0,ambiguous=False)])])
        with patch(MODULE+'Probe.pair',side_effect=ValueError('depth_overlap_pixel_budget')):
            result,report=build(doc,files,'test',depth,dict(regions=[dict(slot='b',group='mixed')]),None)
        self.assertEqual(report['unmeasured_samples'],1)
        self.assertTrue(result['pairs'][-1]['samples'][0]['ambiguous'])


if __name__=='__main__': unittest.main()
