"""Baseline predictions are unchanged legacy results, never manual truth."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.benchmark.joint_baseline import build_joint_baseline, validate_joint_baseline
from autospine_workbench.benchmark.joint_draft import JOINTS
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.resolved_project import canonical_sha256


def inputs():
    audit = {"canvas": [200, 400], "sha256": "a" * 64, "layers": []}
    candidate = {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none",
                 "canvas": audit["canvas"], "coordinate_system": "psd_canvas",
                 "source_psd_sha256": audit["sha256"], "audit_snapshot_sha256": canonical_sha256(audit)}
    return candidate, audit


class JointBaselineTests(unittest.TestCase):
    def test_schema_matches_compiler(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/benchmark-joint-baseline-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(build_joint_baseline(*inputs()))

    def test_pure_no_filesystem_discovery_or_constructor(self):
        candidate, audit = inputs()
        before = deepcopy((candidate, audit))
        with patch.object(ProjectStore, '__init__', side_effect=AssertionError('constructor')), \
                patch.object(ProjectStore, '_discover', side_effect=AssertionError('discovery')), \
                patch.object(Path, 'open', side_effect=AssertionError('filesystem')), \
                patch.object(Path, 'resolve', side_effect=AssertionError('resolve')):
            doc = build_joint_baseline(candidate, audit)
            self.assertEqual(validate_joint_baseline(candidate, audit, doc), doc)
        self.assertEqual((candidate, audit), before)
        self.assertEqual([r['joint_id'] for r in doc['records']], list(JOINTS))
        self.assertEqual(doc['authority'], 'none')
        self.assertIn('character_sides_unreviewed', doc['reason_codes'])

    def test_matches_legacy_empty_layer_fallback_exactly(self):
        candidate, audit = inputs()
        skeleton = object.__new__(ProjectStore)._skeleton(200, 400, [])
        original = {r['id']: r for r in skeleton['joints']}
        doc = build_joint_baseline(candidate, audit)
        for row in doc['records']:
            legacy = original[row['joint_id']]
            self.assertEqual(row['position'], [legacy['x'], legacy['y']])
            self.assertEqual(row['heuristic_score'], legacy['confidence'])
            self.assertEqual(row['source'], legacy['source'])
            self.assertEqual(row['score_kind'], 'heuristic')

    def test_layer_bbox_drives_legacy_prediction(self):
        candidate, audit = inputs()
        before = build_joint_baseline(candidate, audit)
        audit['layers'] = [{'kind': 'pixel', 'name': 'torso', 'bbox': [20, 40, 120, 200]}]
        candidate['audit_snapshot_sha256'] = canonical_sha256(audit)
        after = build_joint_baseline(candidate, audit)
        self.assertNotEqual(before['records'][2]['position'], after['records'][2]['position'])
        self.assertEqual(after['records'][2]['source'], 'layer')

    def test_tamper_rejected_and_audit_identity_checked(self):
        candidate, audit = inputs()
        for mutate in (lambda d: d.update(authority='human'), lambda d: d['records'][0].update(position=[0, 0]),
                       lambda d: d['records'][0].update(heuristic_score=True), lambda d: d.update(extra=1)):
            doc = build_joint_baseline(candidate, audit)
            mutate(doc)
            with self.assertRaisesRegex(ValueError, 'baseline_mismatch'):
                validate_joint_baseline(candidate, audit, doc)
        audit['canvas'] = [100, 100]
        with self.assertRaisesRegex(ValueError, 'audit_mismatch'):
            build_joint_baseline(candidate, audit)


if __name__ == '__main__':
    unittest.main()
