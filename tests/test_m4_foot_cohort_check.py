from copy import deepcopy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from m4_foot_cohort_check import summarize,save_exact


def fixture():
    return {name:dict(job_id=name,artifact_sha256=name,motion_identity={'source':'same'},
        maximum_key_matrix_error=1e-15,maximum_ankle_shift_from_foot_channels_px=0,
        source_contact_markers_preserved=True,key_samples=120,timeline_samples=500,
        geometry_passed=False,contact_status='ankle_proxy_passed',runtime={},
        geometry_failures=[{'slot':'arm'}])for name in ('a','b','c')}


class FootCohortTests(unittest.TestCase):
    def test_resume_preserves_exact_receipt_and_rejects_replacement(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'receipt.json'
            save_exact(path,{'candidate':'a'});before=path.read_bytes()
            save_exact(path,{'candidate':'a'})
            with self.assertRaisesRegex(ValueError,'receipt_changed'):save_exact(path,{'candidate':'b'})
            self.assertEqual(path.read_bytes(),before)

    def test_foot_success_does_not_hide_geometry_failure(self):
        report=summarize(fixture())
        self.assertEqual(report['foot_frame_passed'],3)
        self.assertEqual(report['geometry_passed'],0)
        self.assertFalse(report['selected'])

    def test_source_mismatch_and_duplicate_jobs_rejected(self):
        reports=fixture();reports['b']['motion_identity']={'source':'other'}
        with self.assertRaisesRegex(ValueError,'identity_mismatch'):summarize(reports)
        reports=fixture();reports['b']['job_id']='a'
        with self.assertRaisesRegex(ValueError,'distinct'):summarize(reports)

    def test_nonfinite_or_changed_markers_do_not_pass(self):
        for key,value in [('maximum_key_matrix_error',float('nan')),
                          ('maximum_ankle_shift_from_foot_channels_px',1),
                          ('source_contact_markers_preserved',False)]:
            reports=deepcopy(fixture());reports['b'][key]=value
            self.assertEqual(summarize(reports)['foot_frame_passed'],2)
