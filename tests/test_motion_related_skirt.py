from copy import deepcopy
import unittest
from autospine_workbench.automation.motion_related_skirt import summary


class RelatedSkirtTests(unittest.TestCase):
    def setUp(self):
        self.audit=dict(profile='leg-skirt-surface-envelope-probe-v1',
            artifact_sha256='a'*64,skeleton_sha256='b'*64,source_identity={'clip':'c'*64},
            authority='none',selected=False,order_changed=False,production_authorized=False,
            all_frames_checked=False,times=[0,1],rows=[dict(time=1,pair=['leg','skirt'],
                status='requires_partition_or_more_depth',counts={'back':2,'ambiguous':1})])

    def check(self):return summary(self.audit,'a'*64,'b'*64,{'clip':'c'*64},1)

    def test_hypothesis_does_not_establish_order_or_full_motion_pass(self):
        before=deepcopy(self.audit);r=self.check()
        self.assertEqual(r['status'],'requires_review');self.assertFalse(r['all_frames_checked'])
        self.assertFalse(r['order_changed']);self.assertEqual(self.audit,before)

    def test_wrong_candidate_source_or_skeleton_rejected(self):
        for key in ('artifact_sha256','skeleton_sha256','source_identity'):
            old=self.audit[key];self.audit[key]='e'*64
            with self.assertRaisesRegex(ValueError,'identity'):self.check()
            self.audit[key]=old

    def test_overclaim_time_and_counts_rejected(self):
        self.audit['all_frames_checked']=True
        with self.assertRaisesRegex(ValueError,'scope'):self.check()
        self.audit['all_frames_checked']=False;self.audit['rows'][0]['time']=2
        with self.assertRaisesRegex(ValueError,'row'):self.check()
        self.audit['rows'][0]['time']=1;self.audit['rows'][0]['counts']['ambiguous']=-1
        with self.assertRaisesRegex(ValueError,'counts'):self.check()
