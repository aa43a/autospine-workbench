import unittest
import numpy as np
import tempfile
from pathlib import Path
from autospine_workbench.benchmark.seam_gap_context_cli import load, analyze
from autospine_workbench.targets.spine43.seam_gap_context import classify


class GapContextTests(unittest.TestCase):
    def masks(self):
        a = np.zeros((13, 13), dtype=bool)
        b = a.copy(); gap = a.copy(); gap[6, 6] = True
        return a, b, gap

    def test_open_crack_still_has_opposed_support(self):
        a, b, gap = self.masks(); a[:, 5] = True; b[:, 7] = True
        counts, _ = classify(a, b, gap)
        self.assertEqual(counts['opposed_attachment_support'], 1)

    def test_single_support_is_evidence_not_approval(self):
        a, b, gap = self.masks(); a[:, 5] = True
        counts, _ = classify(a, b, gap)
        self.assertEqual(counts['single_attachment_support'], 1)

    def test_overlap_and_missing_support_are_uncertain(self):
        a, b, gap = self.masks()
        self.assertEqual(classify(a, b, gap)[0]['uncertain'], 1)
        a[:, 5] = True; b[:, 5] = True
        self.assertEqual(classify(a, b, gap)[0]['uncertain'], 1)

    def test_roi_edge_is_not_exterior_proof(self):
        a, b, gap = self.masks(); gap[:] = False; gap[0, 6] = True; a[:, 5] = True
        self.assertEqual(classify(a, b, gap)[0]['uncertain'], 1)

    def test_swap_reflect_and_partition(self):
        a, b, gap = self.masks(); a[:, 5] = True; b[:, 7] = True
        counts, labels = classify(a, b, gap)
        self.assertEqual(counts, classify(b, a, gap)[0])
        np.testing.assert_array_equal(labels[:, ::-1], classify(a[:, ::-1], b[:, ::-1], gap[:, ::-1])[1])
        self.assertEqual(sum(counts.values()), int(gap.sum()))

    def test_invalid_input(self):
        a, b, gap = self.masks()
        with self.assertRaises(ValueError): classify(a.astype(float), b, gap)
        with self.assertRaises(ValueError): classify(a, b, gap, 8)
        a[6, 6] = True
        with self.assertRaises(ValueError): classify(a, b, gap)

    def test_source_identity_and_file_tamper_fail_closed(self):
        before = {'schema': 'autospine.continuous-anchor-preview/v1'}
        after = {'schema': 'autospine.seam-increment-preview/v1', 'source_anchor_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'source_identity'):
            analyze(before, after, Path('.'), Path('.'))
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'skeleton.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'file_hash'):
                load({'files': {'skeleton.json': '0' * 64}}, Path(directory), 'skeleton.json')
            with self.assertRaisesRegex(ValueError, 'gap_context_path'):
                load({}, Path(directory), '../skeleton.json')
