from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.surface_order_evidence import build,merge


def fixture(role='arm.l'):
    inventory=dict(surfaces=[dict(slot='a',role='arm.r'),dict(slot='b',role=role)])
    rows=[dict(arm='a',body='b',time=t,source_tick=t*1e6,status='uniform_back_proxy') for t in (0,.5,1)]
    return inventory,rows,[(0,0),(.5,500000),(1,1000000)]


class SurfaceOrderEvidenceTests(unittest.TestCase):
    def test_other_hand_remains_in_front_and_midpoint_is_attached(self):
        result=build(*fixture());row=result['pairs'][0]['samples'][0]
        self.assertEqual(row['current_front_slot'],'b')
        self.assertEqual(row['interval_sample']['source_tick'],500000)

    def test_visible_unknown_garment_keeps_setup_hold(self):
        result=build(*fixture('garment_plane_candidate'))
        self.assertFalse(result['pairs']);self.assertEqual(result['held'][0]['policy'],'preserve_visible_setup_order')

    def test_missing_or_ambiguous_known_evidence_cannot_turn_into_front(self):
        for status in ('requires_partition_or_more_depth','unmeasured'):
            args=fixture();args[1][1]['status']=status
            self.assertTrue(build(*args)['pairs'][0]['samples'][0]['interval_sample']['ambiguous'])
        args=fixture();args[1].pop(1)
        with self.assertRaisesRegex(ValueError,'time_inventory'):build(*args)

    def test_merge_rejects_disagreement_and_keeps_inputs(self):
        base=build(*fixture());extra=deepcopy(base);before=deepcopy(base)
        self.assertEqual(len(merge(base,extra)['pairs']),1);self.assertEqual(base,before)
        extra['pairs'][0]['samples'][0]['current_front_slot']='a'
        with self.assertRaisesRegex(ValueError,'conflicting_observations'):merge(base,extra)

    def test_all_nonoverlap_has_coverage_receipt_but_no_order_request(self):
        args=fixture()
        for row in args[1]:row['status']='no_overlap'
        result=build(*args)
        self.assertEqual(result['nonoverlap'],[['a','b']]);self.assertFalse(result['pairs'])

    def test_duplicate_supplement_cannot_silently_overwrite(self):
        base=build(*fixture());extra=deepcopy(base);extra['pairs']*=2
        with self.assertRaisesRegex(ValueError,'duplicate_supplement'):merge(base,extra)
