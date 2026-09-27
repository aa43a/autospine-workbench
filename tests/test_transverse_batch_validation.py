from copy import deepcopy
from hashlib import sha256
import json
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_transverse_batch_validation import verify_diagnostic, verify_coverage, prepare
from m4_transverse_sampling_probe import inventory
from test_transverse_workflow import bundle


class TransverseBatchTests(unittest.TestCase):
    def fixture(self):
        files, _ = bundle()
        for key in ('skeleton.json','numeric-reference.json'):
            data = json.loads(files[key]); data['animations']['external-motion'] = data['animations'].pop('motion')
            files[key] = canonical_bytes(data)
        digest = sha256(files['skeleton.json']).hexdigest()
        for key in ('numeric-reference.json','rig-setup-reference.json'):
            data = json.loads(files[key]); data['skeleton_sha256'] = digest; files[key] = canonical_bytes(data)
        doc = json.loads(files['skeleton.json']); times = inventory(doc, 'external-motion', [0,.5,1])['times']
        return files, times, dict(slot='leg', skeleton_sha256=digest,
            times_sha256=sha256(canonical_bytes(times)).hexdigest())

    def test_same_grid_parent_comparison_and_no_inherited_qa(self):
        files, times, report = self.fixture()
        verify_diagnostic(files, files['skeleton.json'], report, times)
        output, qa = prepare(files, files['skeleton.json'], times)
        self.assertNotIn('motion-depth.json', output)
        self.assertNotIn('motion-review.json', output)
        self.assertEqual(output['skeleton.json'], files['skeleton.json'])
        self.assertTrue(all(r['sample_count']==len(times) for r in qa['records']))

    def test_edited_bones_and_missing_time_rejected_even_with_matching_hash(self):
        files, times, report = self.fixture(); doc = json.loads(files['skeleton.json'])
        doc['bones'][0]['x'] = 30; raw = canonical_bytes(doc)
        report['skeleton_sha256'] = sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, 'unselected'):verify_diagnostic(files, raw, report, times)
        report['skeleton_sha256'] = sha256(files['skeleton.json']).hexdigest()
        times = times[:-1]; report['times_sha256'] = sha256(canonical_bytes(times)).hexdigest()
        with self.assertRaisesRegex(ValueError, 'required_times'):
            verify_diagnostic(files, files['skeleton.json'], report, times)

    def test_coverage_retains_geometry_failure_and_rejects_gap_duplicate_identity(self):
        rows = [dict(times=[0,.5], render_identity='same', geometry_passed=True),
                dict(times=[0,1], render_identity='same', geometry_passed=False)]
        value = verify_coverage([0,.5,1], rows)
        self.assertTrue(value['exact_time_coverage']); self.assertFalse(value['geometry_passed'])
        self.assertEqual(value['runtime_status'], 'not_evaluated')
        for changed in (rows[:1], rows+rows[1:], [rows[0], dict(rows[1],render_identity='different')]):
            with self.assertRaisesRegex(ValueError, 'coverage'):verify_coverage([0,.5,1], changed)

    def test_runtime_must_match_actual_times_artifact_and_implementation(self):
        def row(times):
            return dict(times=times,render_identity='same',geometry_passed=False,candidate_bundle_sha256='a',
                runtime=dict(bundle_sha256='a',passed=True,authority='none',production_authorized=False,
                    runtime_sha256='r', runtime_version='4.3.13', profile='official', browser_sha256='browser',
                    harness_sha256='harness', tool_sha256='tool', reference_reader_sha256='reader',
                    results=[dict(time=t,animation='external-motion') for t in times]))
        rows=[row([0,.5]),row([0,1])]
        self.assertEqual(verify_coverage([0,.5,1], rows, True)['runtime_status'], 'passed')
        for key,value in [('bundle_sha256','b'),('passed',False),('runtime_sha256','other'),('tool_sha256',None)]:
            changed=deepcopy(rows);changed[1]['runtime'][key]=value
            with self.assertRaises(ValueError):verify_coverage([0,.5,1],changed,True)
