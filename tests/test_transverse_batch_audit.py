import json
from pathlib import Path
import tempfile
import unittest
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_transverse_batch_validation import run
from m4_transverse_batch_audit import audit
import test_transverse_batch_validation as fixtures


class TransverseBatchAuditTests(unittest.TestCase):
    def build(self, root):
        files, times, receipt = fixtures.TransverseBatchTests().fixture()
        state = root/'state'; digest = AnimatedStore(state).publish(files)
        receipt['parent_artifact_sha256'] = digest
        probe = root/'probe'; probe.mkdir()
        (probe/'report.json').write_bytes(canonical_bytes(receipt))
        (probe/'solved-diagnostic.json').write_bytes(files['skeleton.json'])
        (probe/'validation-times.json').write_bytes(canonical_bytes(times))
        output = root/'batches'; run(state, probe, output)
        return state, probe, output

    def test_real_saved_cpu_batches_are_reconstructable(self):
        with tempfile.TemporaryDirectory() as temp:
            state, probe, output = self.build(Path(temp))
            checked = audit(state, probe, output)
            self.assertTrue(checked['exact_time_coverage'])
            self.assertEqual(checked['runtime_status'], 'not_evaluated')

    def test_changed_geometry_report_and_missing_batch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            state, probe, output = self.build(Path(temp))
            path = output/'batch-000/geometry.json'; raw = path.read_bytes()
            data = json.loads(raw); data['geometry']['passed'] = not data['geometry']['passed']
            path.write_bytes(canonical_bytes(data))
            with self.assertRaisesRegex(ValueError, 'geometry'):audit(state, probe, output)
            path.write_bytes(raw)
            path = output/'report.json'; data = json.loads(path.read_bytes()); data['rows'] = []
            path.write_bytes(canonical_bytes(data))
            with self.assertRaisesRegex(ValueError, 'count'):audit(state, probe, output)

    def test_runtime_snapshot_must_equal_saved_capture_file(self):
        with tempfile.TemporaryDirectory() as temp:
            state, probe, output = self.build(Path(temp))
            path = output/'report.json'; data = json.loads(path.read_bytes()); row = data['rows'][0]
            # Synthetic capture tests the audit contract, not official GPU behavior.
            capture = dict(bundle_sha256=row['candidate_bundle_sha256'], passed=True,
                authority='none',production_authorized=False,runtime_sha256='r',runtime_version='4.3.13',
                profile='official',browser_sha256='b',harness_sha256='h',tool_sha256='t',reference_reader_sha256='reader',
                results=[dict(animation='external-motion',time=t) for t in row['times']])
            row['runtime'] = capture; data['coverage']['runtime_status'] = 'passed'
            path.write_bytes(canonical_bytes(data))
            runtime_dir=output/'batch-000/runtime';runtime_dir.mkdir()
            runtime_path=runtime_dir/'report.json';runtime_path.write_bytes(canonical_bytes(capture))
            self.assertEqual(audit(state,probe,output)['runtime_status'],'passed')
            capture['results'][0]['time']=.1;runtime_path.write_bytes(canonical_bytes(capture))
            with self.assertRaisesRegex(ValueError,'runtime'):audit(state,probe,output)
