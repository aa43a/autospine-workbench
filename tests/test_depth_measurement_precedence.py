from copy import deepcopy
from hashlib import sha256
import json
import unittest

from autospine_workbench.targets.character43.depth_failure_records import collect
from autospine_workbench.targets.character43.depth_measurement_precedence import superseded


def fixture():
    check = dict(time=1, pair=['body', 'arm'], status='requires_partition_or_more_depth',
                 overlap_pixels=4, counts=dict(front=0, back=0, ambiguous=1, unknown=3))
    legacy = dict(tick=1_000_000, overlap=dict(status='unmeasured', reason_code='depth_overlap_pixel_budget'))
    return dict(profile='external-regional-depth-order-v1',
                pairs=[dict(arm_slot='arm', torso_slot='body', samples=[legacy])],
                regional=dict(refinement=dict(rows=[dict(pair=['arm', 'body'], checks=[check])])),
                order=dict(failures=[dict(time=1, pair=['arm', 'body'], reason_code='visible_depth_straddle')]))


class MeasurementPrecedenceTests(unittest.TestCase):
    def test_operator_status_reports_supersession_without_acceptance(self):
        from autospine_workbench.targets.character43.motion_depth_status import build
        depth=fixture();depth['skeleton_sha256']=sha256(b'{}').hexdigest()
        depth['regional']['unmeasured_samples']=0
        files={'skeleton.json':b'{}','motion-depth.json':json.dumps(depth).encode()}
        before=deepcopy(files);report=build(files,'artifact')
        self.assertEqual(report['superseded_legacy_overlap_samples'],1)
        self.assertEqual(report['failure_record_counts'],{'depth_conflict':1})
        self.assertEqual(report['status'],'needs_changes')
        self.assertFalse(report['production_authorized'])
        self.assertEqual(files,before)

    def test_completed_uncertainty_replaces_only_legacy_unmeasured(self):
        depth=fixture(); before=deepcopy(depth)
        self.assertEqual(superseded(depth), {(('arm','body'),1)})
        self.assertEqual(collect(depth), depth['order']['failures'])
        self.assertEqual(depth,before)

    def test_different_pair_time_or_profile_cannot_replace(self):
        for field,value in [('time',1.000001),('pair',['arm','other']),('status','future_status')]:
            depth=fixture();depth['regional']['refinement']['rows'][0]['checks'][0][field]=value
            self.assertFalse(superseded(depth));self.assertEqual(len(collect(depth)),2)
        depth=fixture();depth['profile']='legacy'
        self.assertFalse(superseded(depth))

    def test_incomplete_or_inconsistent_duplicate_keeps_pending(self):
        for change in (dict(status='unmeasured'),dict(overlap_pixels=5),
                       dict(counts=dict(front=1,back=0,ambiguous=0,unknown=3))):
            depth=fixture();checks=depth['regional']['refinement']['rows'][0]['checks']
            checks.append(dict(checks[0],**change))
            self.assertFalse(superseded(depth))

    def test_duplicate_complete_and_empty_overlap_are_supported(self):
        depth=fixture();checks=depth['regional']['refinement']['rows'][0]['checks']
        checks.append(deepcopy(checks[0]));self.assertEqual(len(superseded(depth)),1)
        for c in checks:c.update(status='no_overlap',overlap_pixels=0,counts={})
        self.assertEqual(len(superseded(depth)),1)
        checks[0]['overlap_pixels']=True
        self.assertFalse(superseded(depth))

    def test_order_limit_and_independent_cloth_limit_are_preserved(self):
        depth=fixture()
        depth['order']['failures'].append(dict(time=1,pair=['arm','body'],reason_code='depth_overlap_pixel_budget'))
        depth['regional']['cloth_constraints']=dict(pairs=[dict(arm='arm',cloth='cloth',rows=[dict(checks=[
            dict(time=1,status='unmeasured',reason_code='depth_overlap_pixel_budget')])])])
        rows=collect(depth)
        self.assertEqual(len(rows),3)
        self.assertEqual(sum(r['reason_code']=='depth_overlap_pixel_budget' for r in rows),2)


if __name__=='__main__':unittest.main()
