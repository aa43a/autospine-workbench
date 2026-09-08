"""Candidate collection cannot broaden evidence or serve unverified files."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from autospine_workbench.benchmark.seam_candidate_hub import bundle_bytes, summarize
from autospine_workbench.resolved_project import canonical_sha256


class CandidateHubTests(unittest.TestCase):
    def setUp(self):
        self.candidate = dict(schema='autospine.seam-stable-fallback/v1', authority='none',
                              production_authorized=False, followers=['left'])
        self.admission = dict(authority='none', production_authorized=False,
                              source_candidate_sha256=canonical_sha256(self.candidate), relations=[
                                  dict(follower='left', status='sampled_no_new_regression', sample_count=7),
                                  dict(follower='right', status='not_evaluated', sample_count=0)])

    def test_selection_preserves_missing_coverage_and_inputs(self):
        original = deepcopy(self.admission)
        result = summarize('alice', self.candidate, self.admission)
        self.assertEqual([r['track'] for r in result['relations']], ['reference', 'increment'])
        self.assertEqual(result['relations'][1]['status'], 'not_evaluated')
        self.assertFalse(result['production_authorized'])
        self.assertEqual(result['status'], 'needs_review')
        self.assertEqual(self.admission, original)

    def test_stale_candidate_evidence_rejected(self):
        self.candidate['followers'].append('right')
        with self.assertRaisesRegex(ValueError, 'identity'):
            summarize('alice', self.candidate, self.admission)

    def test_authority_cannot_be_imported(self):
        self.admission['production_authorized'] = True
        with self.assertRaisesRegex(ValueError, 'review_only'):
            summarize('alice', self.candidate, self.admission)

    def test_inventory_tamper_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'image.png').write_bytes(b'original')
            digest = hashlib.sha256(b'original').hexdigest()
            self.assertEqual(bundle_bytes(folder, {'image.png': digest}), {'image.png': b'original'})
            for name in ('../image.png', '/image.png', 'E:/image.png', '..\\image.png'):
                with self.assertRaisesRegex(ValueError, 'file_path'):
                    bundle_bytes(folder, {name: digest})
            (folder / 'image.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'file_hash'):
                bundle_bytes(folder, {'image.png': digest})


if __name__ == '__main__':
    unittest.main()
