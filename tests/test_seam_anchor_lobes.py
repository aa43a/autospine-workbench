"""Exact-lobe isolation tests for static seam candidate sampling."""

from __future__ import annotations

from dataclasses import replace
import unittest

from autospine_workbench.contact_geometry import contact_between_runs
from autospine_workbench.seam_anchor_lobes import (
    SeamAnchorLobeError,
    isolate_overlap_lobe_runs,
)


class SeamAnchorLobeTests(unittest.TestCase):
    def test_nested_disconnected_pixel_is_not_sampled_with_outer_lobe(self):
        rows = [(0, 0, 10)]
        for y in range(1, 10):
            rows.append((y, 0, 0))
            if 3 <= y <= 7:
                rows.append((y, 3, 7))
            rows.append((y, 10, 10))
        rows.append((10, 0, 10))
        runs = tuple(rows)
        contacts = contact_between_runs(runs, runs).contacts
        self.assertEqual([40, 25], [item.area for item in contacts])
        contact = contacts[0]
        isolated = isolate_overlap_lobe_runs(runs, runs, contact)
        self.assertFalse(any(3 <= y <= 7 and x0 == 3 and x1 == 7
                             for y, x0, x1 in isolated))
        self.assertEqual(contact.area, sum(
            x1 - x0 + 1 for _, x0, x1 in isolated
        ))

    def test_tampered_or_non_overlap_evidence_fails_closed(self):
        runs = ((0, 0, 20),)
        overlap = contact_between_runs(runs, runs).contacts[0]
        with self.assertRaisesRegex(SeamAnchorLobeError, "exactly one"):
            isolate_overlap_lobe_runs(
                runs, runs, replace(overlap, area=overlap.area + 1)
            )
        gap = contact_between_runs(
            ((0, 0, 0),), ((0, 2, 2),), max_gap=2
        ).contacts[0]
        with self.assertRaisesRegex(SeamAnchorLobeError, "invalid"):
            isolate_overlap_lobe_runs(runs, runs, gap)


if __name__ == "__main__":
    unittest.main()
