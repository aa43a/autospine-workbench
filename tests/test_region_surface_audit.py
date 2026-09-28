from copy import deepcopy
import unittest
from m4_region_surface_audit import verify


def fixture():
    rows=[dict(arm='a',body='b',time=t,source_tick=t*1e6,status='unmeasured') for t in (0,.5,1)]
    report=dict(regions=['a'],inventory=dict(surfaces=[dict(slot='a',role='arm.r'),dict(slot='b',role='unmodeled')]),
        pairs=[dict(arm='a',body='b',role='unmodeled',status_counts={'unmeasured':3},sampled_frames=3)],
        sampled_frames=3,status_counts={'unmeasured':3})
    return report,rows,[(0,0),(.5,500000),(1,1000000)]


class RegionSurfaceAuditTests(unittest.TestCase):
    def test_complete_unknowns_are_not_converted_to_depth_success(self):
        result=verify(*fixture())
        self.assertEqual(result['checks'],3)
        self.assertEqual(result['counts'],{'unmeasured':3})

    def test_missing_pair_and_duplicated_pair_reject(self):
        args=fixture();args[0]['pairs']=[]
        with self.assertRaisesRegex(ValueError,'pair_inventory'):verify(*args)
        args=fixture();args[0]['pairs']*=2
        with self.assertRaisesRegex(ValueError,'pair_inventory'):verify(*args)

    def test_missing_duplicate_and_shifted_times_reject(self):
        for mode in ('missing','duplicate','shifted'):
            args=fixture()
            if mode=='missing':args[1].pop(1)
            elif mode=='duplicate':args[1][1]=deepcopy(args[1][0])
            else:args[1][1]['source_tick']+=1
            with self.assertRaisesRegex(ValueError,'time_inventory'):verify(*args)

    def test_counts_and_roles_are_not_trusted(self):
        args=fixture();args[0]['pairs'][0]['role']='torso'
        with self.assertRaisesRegex(ValueError,'coverage_role'):verify(*args)
        args=fixture();args[0]['status_counts']={'uniform_front_proxy':3}
        with self.assertRaisesRegex(ValueError,'total_counts'):verify(*args)
