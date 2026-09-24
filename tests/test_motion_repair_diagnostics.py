"""Worker failures stay bounded; repair summaries preserve candidate evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_intake_process import failure_reason, REPAIR_FAILURES
from autospine_workbench.automation.motion_target_jobs import review_file


class RepairDiagnosticsTests(unittest.TestCase):
    def test_known_failures_and_untrusted_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'worker.log'
            for reason in REPAIR_FAILURES | {'motion_decode_timeout', 'character_invalid'}:
                path.write_text('progress\n' + json.dumps(dict(reason_code=reason)), encoding='utf-8')
                self.assertEqual(failure_reason(path), reason)
            for value in [dict(reason_code='runtime_storage_C:/private/file'),
                          dict(reason_code='material_scene_arbitrary_secret'),
                          dict(reason_code='pose_patch_private_path'),
                          dict(reason_code=['runtime_storage_alpha_unsupported']), [], None, 12]:
                path.write_text(json.dumps(value), encoding='utf-8')
                self.assertEqual(failure_reason(path), 'motion_decode_failed')

    def test_only_recent_bounded_failure_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'worker.log'
            path.write_text('{"reason_code":"runtime_storage_alpha_unsupported"}\n' + 'x\n' * 3000)
            self.assertEqual(failure_reason(path), 'motion_decode_failed')

    def test_summary_material_and_legacy_profiles(self):
        for material in [None, dict(selected_triangles=[1, 3], interval=[1, 2], geometry_unchanged=True)]:
            repair = dict(slot='arm', parent_geometry=dict(passed=False), geometry=dict(passed=False),
                          profile='test', material=material)
            files = {'motion-repair.json': json.dumps(repair).encode(),
                     'motion-repair-provenance.json': b'{"parent_job_id":"parent","parent_artifact_sha256":"old"}'}
            with patch('autospine_workbench.automation.motion_target_jobs.context', return_value=({'artifact_sha256': 'new'}, files)):
                raw, mime = review_file(None, 'job', ['repair-summary.json'])
            report = json.loads(raw)
            self.assertEqual(report['material'], material)
            self.assertFalse(report['after']['passed'])
            self.assertFalse(report['selected'])
            self.assertEqual(report['authority'], 'none')
            self.assertEqual(mime, 'application/json')

    def test_pose_summary_keeps_authored_times_and_scope(self):
        from test_pose_geometry_candidate import bundle
        from autospine_workbench.targets.character43.pose_geometry_candidate import build
        files, plan = bundle()
        output, _, _ = build(files, plan)
        output['motion-repair-provenance.json'] = b'{"parent_job_id":"parent","parent_artifact_sha256":"old"}'
        with patch('autospine_workbench.automation.motion_target_jobs.context', return_value=({'artifact_sha256':'new'}, output)):
            raw, _ = review_file(None, 'job', ['repair-summary.json'])
        report = json.loads(raw)
        self.assertEqual(report['pose_geometry']['times'], [1])
        self.assertEqual(report['pose_geometry']['vertices'], 1)
        self.assertEqual(report['pose_geometry']['interval'], [0, 2])
        self.assertLess(report['pose_geometry']['authored_point_error_px'], 1e-6)
        self.assertFalse(report['selected'])
