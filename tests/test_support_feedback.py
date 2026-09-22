from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from m4_support_feedback import load


class FeedbackIdentityTests(unittest.TestCase):
    def probe(self, *, source='source', bundle='artifact', passed=True, runtime_times=(0,1)):
        with TemporaryDirectory() as root:
            folder=Path(root);(folder/'runtime').mkdir()
            (folder/'report.json').write_text(json.dumps(dict(source_job_id='job',
                source_candidate_sha256=source,candidate_bundle_sha256='artifact')))
            (folder/'runtime/report.json').write_text(json.dumps(dict(bundle_sha256=bundle,passed=passed,
                results=[dict(animation='external-motion',time=t) for t in runtime_times])))
            numeric=dict(skeleton_sha256=sha256(b'skeleton').hexdigest(),
                animations={'external-motion':[dict(time=0),dict(time=1)]})
            with patch('m4_support_feedback.AnimatedStore') as store, patch('m4_support_feedback.read',return_value=numeric):
                store.return_value.read.return_value={'skeleton.json':b'skeleton'}
                return load(folder,'job','source')

    def test_matching_runtime_samples_have_no_acceptance_authority(self):
        times,evidence=self.probe()
        self.assertEqual(times,[0,1]);self.assertEqual(evidence['authority'],'none')

    def test_wrong_source_rejected(self):
        with self.assertRaisesRegex(ValueError,'source_mismatch'):self.probe(source='other')

    def test_wrong_bundle_or_failed_runtime_rejected(self):
        for change in (dict(bundle='other'),dict(passed=False)):
            with self.assertRaisesRegex(ValueError,'runtime_identity_mismatch'):self.probe(**change)

    def test_time_inventory_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'time_grid_mismatch'):self.probe(runtime_times=(0,.5,1))
