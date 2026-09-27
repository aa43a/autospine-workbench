from copy import deepcopy
from hashlib import sha256
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_transverse_batch_validation import verify_diagnostic,normalized_diagnostic
import test_transverse_batch_validation as fixtures


class BoundaryRuntimeInputTests(unittest.TestCase):
    def fixture(self):
        files,times,report=fixtures.TransverseBatchTests().fixture()
        times=sorted(set(times)|{.371})
        source=dict(profile='joint-boundary-animation-v1-experiment',local_constraints_passed=True,
            failures=[],solver_failures=[],authority='none',selected=False,production_authorized=False,
            slot='leg',parent_artifact_sha256='parent',skeleton_sha256=report['skeleton_sha256'],times=times)
        report.update(profile='joint-boundary-runtime-input-v1',boundary_report=source,
            parent_artifact_sha256='parent',boundary_report_sha256=sha256(canonical_bytes(source)).hexdigest(),
            times_sha256=sha256(canonical_bytes(times)).hexdigest())
        return files,times,report

    def test_retains_historical_times_outside_regular_inventory(self):
        files,times,report=self.fixture()
        _,required,_=normalized_diagnostic(files,files['skeleton.json'],report,times)
        self.assertTrue(set(times)<=set(required));self.assertIn(.371,required)

    def test_rejects_failed_or_reidentified_local_report_even_with_updated_digest(self):
        files,times,report=self.fixture()
        for field,value in [('local_constraints_passed',False),('failures',[1]),('solver_failures',[1]),
                            ('parent_artifact_sha256','other'),('selected',True)]:
            changed=deepcopy(report);changed['boundary_report'][field]=value
            changed['boundary_report_sha256']=sha256(canonical_bytes(changed['boundary_report'])).hexdigest()
            with self.assertRaisesRegex(ValueError,'local_evidence'):
                verify_diagnostic(files,files['skeleton.json'],changed,times)

    def test_missing_historical_sample_rejected_despite_matching_times_digest(self):
        files,times,report=self.fixture();times=[t for t in times if t!=.371]
        report['times_sha256']=sha256(canonical_bytes(times)).hexdigest()
        with self.assertRaisesRegex(ValueError,'missing_times'):
            verify_diagnostic(files,files['skeleton.json'],report,times)
