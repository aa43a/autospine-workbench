import unittest
from copy import deepcopy
from hashlib import sha256
from autospine_workbench.automation.motion_related_depth import summary


class RelatedDepthTests(unittest.TestCase):
    def setUp(self):
        self.files={'skeleton.json':b'{"slots":[{"name":"arm"},{"name":"torso"}]}'}
        self.audit=dict(candidate_bundle_sha256='a'*64,
            skeleton_sha256=sha256(self.files['skeleton.json']).hexdigest(),authority='none',selected=False,
            depth=dict(profile='external-arm-torso-depth-review-v1',authority='none',selected=False,
                       source_sha256='s',map_sha256='m'),
            order=dict(profile='external-overlap-guarded-draw-order-v1',authority='none',selected=False,
                       failures=[dict(time=.033333,pair=['arm','torso'],reason_code='visible_depth_straddle')]))
        self.value=dict(candidate_sha256='a'*64,runtime=dict(results=[dict(time=1)]),
                        receipt=dict(source_identity=dict(raw_bvh_sha256='s',bvh_map_sha256='m'),depth_audit=self.audit))

    def test_exact_diagnostic_preserves_inputs_and_time(self):
        old=deepcopy(self.value)
        result=summary(self.value,self.files)
        self.assertEqual(result['status'],'needs_changes')
        self.assertEqual(result['failures'][0]['time'],.033333)
        self.assertEqual(self.value,old)
        self.audit['order']['failures']=[]
        self.assertEqual(summary(self.value,self.files)['status'],'requires_review')

    def test_foreign_candidate_source_skeleton_and_authority_rejected(self):
        for path in [('candidate_bundle_sha256',),('skeleton_sha256',),('depth','source_sha256'),
                     ('depth','map_sha256'),('order','selected')]:
            with self.subTest(path=path):
                value=deepcopy(self.value);obj=value['receipt']['depth_audit']
                for k in path[:-1]:obj=obj[k]
                obj[path[-1]]='changed'
                with self.assertRaises(ValueError):summary(value,self.files)

    def test_bad_locations_rejected(self):
        for change in [dict(time=float('nan')),dict(time=2),dict(time=-1),dict(time=True),
                       dict(pair=['arm','foreign'])]:
            with self.subTest(change=change):
                value=deepcopy(self.value);value['receipt']['depth_audit']['order']['failures'][0].update(change)
                with self.assertRaisesRegex(ValueError,'failure_location'):summary(value,self.files)

    def test_legacy_receipt_without_diagnostic_still_reads(self):
        self.value['receipt'].pop('depth_audit')
        self.assertIsNone(summary(self.value,self.files))

    def test_cycle_preserves_complete_location_and_rejects_invalid_edges(self):
        row=dict(time=.2,reason_code='visible_unmapped_order_conflict',conflict=dict(
            slots=['arm','torso','arm'],edges=[dict(back='arm',front='torso'),dict(back='torso',front='arm')]))
        self.audit['order']['failures']=[row];before=deepcopy(self.value)
        result=summary(self.value,self.files)['failures']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['location_kind'],'order_cycle')
        self.assertEqual(result[0]['conflict_slots'],['arm','torso','arm'])
        self.assertEqual(self.value,before)
        for change in [dict(slots=['arm','foreign','arm']),dict(slots=['arm','torso']),
                       dict(edges=[dict(back='torso',front='arm'),dict(back='arm',front='torso')])]:
            value=deepcopy(before);value['receipt']['depth_audit']['order']['failures'][0]['conflict'].update(change)
            with self.assertRaisesRegex(ValueError,'failure_location'):summary(value,self.files)

    def test_missing_coverage_is_unknown_and_bad_counts_rejected(self):
        self.assertIsNone(summary(self.value,self.files)['coverage'])
        coverage=dict(visible_pair_samples=134,ambiguous_visible_pair_samples=32,
                      order_mismatch_pair_samples=69,unmeasured_pair_samples=110)
        self.audit['depth']['target_overlap']=coverage
        before=deepcopy(self.value)
        self.assertEqual(summary(self.value,self.files)['coverage'],coverage)
        self.assertEqual(before,self.value)
        for bad in (-1,True,1.5,None):
            coverage['unmeasured_pair_samples']=bad
            with self.assertRaisesRegex(ValueError,'depth_coverage'):summary(self.value,self.files)

    def test_budget_location_can_be_nested_but_must_match_time_and_slots(self):
        row=dict(time=.2,reason_code='depth_overlap_pixel_budget',
                 raster_budget=dict(time=.2,pair=['arm','torso']))
        self.audit['order']['failures']=[row]
        self.assertEqual(summary(self.value,self.files)['failures'][0]['pair'],['arm','torso'])
        row['raster_budget']['time']=.3
        with self.assertRaisesRegex(ValueError,'failure_location'):summary(self.value,self.files)
        row['raster_budget'].update(time=.2,pair=['arm','foreign'])
        with self.assertRaisesRegex(ValueError,'failure_location'):summary(self.value,self.files)
