from copy import deepcopy
from types import SimpleNamespace
import unittest
from m4_supplement_garment_trace import extend


class GarmentTraceTests(unittest.TestCase):
    def test_reuses_unique_times_and_preserves_originals(self):
        traces={'arm':[dict(body=b,time=t,source_tick=t+100,triangles={},status='no_overlap')
                       for b in ['chest','front'] for t in [0,1]]};original=deepcopy(traces);calls=[]
        def check(a,b,t,source_tick,on_triangle):
            calls.append((a,b,t,source_tick));on_triangle(2,dict(front=5))
            return dict(status='uniform_front_proxy',time=t)
        result,checks=extend(traces,['skirt'],SimpleNamespace(check=check))
        self.assertEqual(traces,original);self.assertEqual(len(calls),2)
        self.assertEqual([c[3] for c in calls],[100,101]);self.assertEqual(len(checks),2)
        self.assertEqual(result['arm'][-1]['triangles'],{2:{'front':5}})

    def test_partial_failure_is_unknown_and_duplicate_relations_rejected(self):
        traces={'arm':[dict(body='chest',time=0,source_tick=100,triangles={},status='no_overlap')]}
        def check(*args,on_triangle):
            on_triangle(2,dict(front=5));raise ValueError('budget')
        result,checks=extend(traces,['skirt'],SimpleNamespace(check=check))
        self.assertEqual(result['arm'][-1]['triangles'],{})
        self.assertEqual(result['arm'][-1]['status'],'unmeasured')
        self.assertEqual(checks[0]['reason_code'],'budget')
        with self.assertRaisesRegex(ValueError,'duplicate_pair'):extend(traces,['chest'],None)
        with self.assertRaisesRegex(ValueError,'selected_slots'):extend(traces,['arm'],None)
        traces['arm'].append(dict(body='front',time=0,source_tick=101))
        with self.assertRaisesRegex(ValueError,'source_time_conflict'):extend(traces,['skirt'],None)


if __name__=='__main__':unittest.main()
