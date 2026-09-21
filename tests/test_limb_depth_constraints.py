from copy import deepcopy
import unittest
from unittest.mock import Mock,patch
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.limb_depth_constraints import build
from autospine_workbench.targets.character43.motion_depth_overlap import Probe

MODULE='autospine_workbench.targets.character43.limb_depth_constraints.'


class LimbConstraintTests(unittest.TestCase):
    def test_no_identified_leg_slots_adds_no_constraint(self):
        doc,files=fixture(); depth=dict(groups={'left':['a'],'right':[]},pairs=[])
        result,report=build(doc,files,'test',depth,None)
        self.assertEqual(result,depth)
        self.assertEqual(report['status'],'not_applicable')
        self.assertEqual(report['pair_count'],0)

    def run_case(self,statuses,sparse=False):
        doc,files=fixture(); doc['slots'][1]['bone']='thigh_r'
        doc['bones'].append(dict(name='thigh_r',parent='root',length=2,x=0,y=0,rotation=0))
        depth=dict(groups={'left':['a'],'right':[]},pairs=[dict(samples=[
            dict(tick=t,source_tick=t+200000,ambiguous=False) for t in (0,100000)])])
        before=deepcopy(depth); sampler=Mock(return_value={}); sampler.leg_segments.return_value={}
        probe=Probe(doc,files,'test',tiled=bool(sparse),sparse=sparse)
        with patch(MODULE+'infer',return_value={'axes':{}}), patch(MODULE+'observe',return_value={'segments':{}}), \
             patch(MODULE+'intervals',return_value={'intervals':[[0,0]]*4}), \
             patch(MODULE+'compare',side_effect=[dict(status=s) for s in statuses]):
            result,report=build(doc,files,'test',depth,sampler,order_probe=probe)
        self.assertEqual(depth,before)
        self.assertEqual([c.args[0] for c in sampler.call_args_list],[200000,250000,300000])
        self.assertEqual(len(probe.results),3)
        return result,report

    def test_sparse_policy_is_shared_by_limb_and_order_probes(self):
        dense,first=self.run_case(['uniform_front_proxy']*3)
        for policy in (True,'tight_triangle_boxes'):
            sparse,second=self.run_case(['uniform_front_proxy']*3,sparse=policy)
            self.assertEqual(dense,sparse)
            self.assertEqual(first['unmeasured_samples'],second['unmeasured_samples'])

    def test_all_visible_samples_agree_and_preserve_original(self):
        result,report=self.run_case(['uniform_front_proxy']*3)
        self.assertEqual(report['frame_count'],2)
        self.assertEqual(report['unmeasured_samples'],0)
        self.assertEqual(result['pairs'][-1]['evidence_source'],'arm_leg_depth_envelope_model')
        self.assertTrue(all(r['current_front_slot']=='a' and not r['ambiguous'] for r in result['pairs'][-1]['samples']))

    def test_midpoint_disagreement_and_unmeasured_remain_blocking(self):
        result,report=self.run_case(['uniform_front_proxy','uniform_back_proxy','unmeasured'])
        self.assertTrue(all(r['ambiguous'] for r in result['pairs'][-1]['samples']))
        self.assertEqual(report['unmeasured_samples'],1)

    def test_foreign_probe_rejected(self):
        doc,files=fixture()
        with self.assertRaisesRegex(ValueError,'probe_identity'):
            build(doc,files,'test',{},None,order_probe=Probe(deepcopy(doc),files,'test'))


if __name__=='__main__': unittest.main()
