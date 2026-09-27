from copy import deepcopy
import unittest
from test_final_motion_contact import fixture
from autospine_workbench.targets.character43.final_motion_contact import recheck
from autospine_workbench.targets.character43.final_contact_batches import inspect


class FinalContactBatchTests(unittest.TestCase):
    def test_split_preserves_exact_result_and_does_not_reset_contact_anchor(self):
        doc,motion=fixture();times=[i/100 for i in range(101)];before=deepcopy((doc,motion))
        expected=recheck(doc,'a',motion,{},times,100)['after']
        result=inspect(doc,'a',motion,{},times,100,batch_size=7)
        self.assertEqual(result['after'],expected);self.assertEqual((doc,motion),before)
        self.assertFalse(result['after']['passed']);self.assertFalse(result['selected'])

    def test_only_middle_batch_contains_short_interval_samples(self):
        doc,motion=fixture();motion['markers'][0].update(start_tick=49,end_tick=52)
        times=[i/100 for i in range(101)]
        result=inspect(doc,'a',motion,{},times,100,batch_size=8)
        self.assertEqual(result['after'],recheck(doc,'a',motion,{},times,100)['after'])
        self.assertEqual([s['time'] for s in result['after']['intervals'][0]['samples']],[.49,.5,.51])

    def test_missing_and_inferred_contacts_keep_evidence_status(self):
        doc,motion=fixture();markers=motion['markers'];motion['markers']=[]
        self.assertIsNone(inspect(doc,'a',motion,{},[0,.5,1],100,batch_size=1)['after']['passed'])
        contact={'hypothesis':dict(ticks_per_second=100,markers=markers)}
        self.assertEqual(inspect(doc,'a',motion,contact,[0,.5,1],100,batch_size=1)['after'],
                         recheck(doc,'a',motion,contact,[0,.5,1],100)['after'])

    def test_invalid_grid_or_batch_budget_rejected(self):
        doc,motion=fixture()
        for times in ([0,.5],[0,.5,.5,1],[0,float('nan'),1]):
            with self.assertRaises(ValueError):inspect(doc,'a',motion,{},times,100)
        with self.assertRaises(ValueError):inspect(doc,'a',motion,{},[0,1],100,batch_size=4096)
