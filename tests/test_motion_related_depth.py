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
