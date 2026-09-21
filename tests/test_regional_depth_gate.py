from hashlib import sha256
import json
import unittest
from test_motion_readiness import fixture
from autospine_workbench.targets.character43.regional_depth_gate import evaluate
from autospine_workbench.targets.character43.motion_readiness import build
from autospine_workbench.targets.character43.motion_depth_status import build as status


class RegionalGateTests(unittest.TestCase):
    def fixture(self):
        files, runtime = fixture(); depth = json.loads(files['motion-depth.json'])
        order = dict(status='no_visible_order_change', failures=[], frames=[])
        depth.update(profile='external-regional-depth-order-v1', selected=True, order=order,
            regional=dict(unmeasured_samples=0, refinement=dict(rows=[]), order=order))
        depth.pop('target_overlap', None)
        files['motion-depth.json'] = json.dumps(depth).encode()
        files['motion-regional-transform.json'] = json.dumps(dict(profile='verified-regional-depth-transform-v1',
            candidate_skeleton_sha256=sha256(files['skeleton.json']).hexdigest())).encode()
        return files, depth, runtime

    def test_regional_evidence_without_legacy_summary(self):
        files, depth, runtime = self.fixture()
        self.assertEqual(evaluate(files, depth), 'sampled_pass')
        row = next(r for r in build(files, 'a'*64, runtime)['stages'] if r['stage'] == '遮挡')
        self.assertEqual(row['status'], 'sampled_pass')
        self.assertEqual(status(files, 'a'*64)['status'], 'sampled_candidate')

    def test_missing_or_changed_transform_never_passes(self):
        files, depth, _ = self.fixture()
        files['skeleton.json'] += b' '
        self.assertEqual(evaluate(files, depth), 'unmeasured')
        del files['motion-regional-transform.json']
        self.assertEqual(evaluate(files, depth), 'unmeasured')

    def test_failed_incomplete_and_unselected_evidence(self):
        for kind in ['failed', 'unmeasured', 'missing', 'unselected', 'divergent']:
            files, depth, _ = self.fixture()
            if kind == 'failed': depth['order']['failures'] = [dict(time=0, reason_code='visible_depth_straddle')]
            elif kind == 'unmeasured': depth['regional']['unmeasured_samples'] = 1
            elif kind == 'missing': del depth['regional']['unmeasured_samples']
            elif kind == 'unselected': depth['selected'] = False
            else: depth['regional']['order'] = {}
            self.assertNotEqual(evaluate(files, depth), 'sampled_pass')
