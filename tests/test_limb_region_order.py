from copy import deepcopy
import unittest
from m4_limb_region_order import constraints


def fixture():
    partition=dict(regions=[dict(slot='hand-region',source_slot='arm',group='hand')])
    source=dict(pairs=[dict(arm_slot='arm',torso_slot='torso',samples=[
        dict(tick=0,source_tick=100),dict(tick=1000000,source_tick=1000100)])])
    diagnosis=dict(rows=[dict(region='hand-region',source_slot='arm',group='hand',body='torso',
        time=t,source_tick=t*1000000+100,status='uniform_front_proxy') for t in (0,.5,1)])
    return diagnosis,partition,source


class LimbRegionOrderTests(unittest.TestCase):
    def test_exact_midpoint_and_source_times_preserved(self):
        inputs=fixture();before=deepcopy(inputs);result=constraints(*inputs)
        self.assertTrue(result['strict_interval_evidence'])
        row=result['pairs'][0]['samples'][0]
        self.assertEqual(row['interval_sample']['source_tick'],500100)
        self.assertEqual(row['current_front_slot'],'hand-region')
        self.assertEqual(inputs,before)

    def test_missing_shifted_or_duplicate_observations_rejected(self):
        for mode in ('missing','shifted','duplicate'):
            inputs=fixture();rows=inputs[0]['rows']
            if mode=='missing':rows.pop(1)
            elif mode=='shifted':rows[1]['source_tick']+=1
            else:rows[1]=deepcopy(rows[0])
            with self.assertRaisesRegex(ValueError,'same_time'):constraints(*inputs)

    def test_uncertainty_is_retained_as_blocking_evidence(self):
        inputs=fixture();inputs[0]['rows'][1]['status']='requires_partition_or_more_depth'
        result=constraints(*inputs)
        self.assertTrue(result['pairs'][0]['samples'][0]['interval_sample']['ambiguous'])

    def test_unrelated_body_is_not_silently_discarded(self):
        inputs=fixture();extra=deepcopy(inputs[0]['rows'][0]);extra['body']='hair'
        inputs[0]['rows'].append(extra)
        with self.assertRaisesRegex(ValueError,'pair_inventory'):constraints(*inputs)
