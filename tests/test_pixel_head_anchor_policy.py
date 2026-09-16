from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.pixel_head_anchor_policy import propose


class PixelHeadTests(unittest.TestCase):
    def evaluate(self, y, *, reasons=None, status='needs_review', bottom=228):
        source = SimpleNamespace(candidate={'layers': [dict(layer_id='face', bbox=[0, 0, 20, bottom])]})
        row = dict(layer_id='face', status=status, reason_codes=reasons or ['face_above_neck'],
                   evidence=dict(face_layer_id='face', neck_point=[10, y]),
                   checks=dict(face_above_neck=False, face_neck_contact=True), option_id=None)
        before = dict(rows=[row])
        with patch('autospine_workbench.automation.pixel_head_anchor_policy.previous', return_value=deepcopy(before)):
            return propose(source)['rows'][0], row

    def test_same_cell_includes_fractional_anchor_and_exact_last_row(self):
        for y in (227, 227.001, 227.849, 227.999):
            row, _ = self.evaluate(y)
            self.assertEqual(row['status'], 'eligible')
            self.assertEqual(row['option_id'], 'rigid:head')
            self.assertTrue(all(row['checks'].values()))

    def test_next_row_gap_is_not_a_tolerance(self):
        for y in (226.999, 226, 200):
            row, before = self.evaluate(y)
            self.assertEqual(row, before)

    def test_preserve_other_failures_manual_state_and_invalid_bounds(self):
        for kwargs in (dict(reasons=['face_above_neck', 'face_neck_contact']),
                       dict(status='preserved'), dict(bottom=228.5)):
            row, before = self.evaluate(227.849, **kwargs)
            self.assertEqual(row, before)

    def test_translation_preserves_pixel_cell_rule(self):
        for offset in (-300, -20, 0, 500):
            row, _ = self.evaluate(227.849 + offset, bottom=228 + offset)
            self.assertEqual(row['status'], 'eligible')
