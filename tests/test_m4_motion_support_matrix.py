"""Execution, partial checks and missing evidence must not imply support."""
import unittest
from m4_motion_support_matrix import gates, coverage, render, STAGES


class SupportMatrixTests(unittest.TestCase):
    def test_execution_and_geometry_do_not_fill_missing_stages(self):
        row = dict(status='succeeded', geometry=True, runtime_frames=100)
        self.assertEqual(set(gates(row).values()), {'unmeasured'})
        self.assertEqual(coverage([row])['Runtime']['unmeasured'], 1)

    def test_unknown_status_is_unknown_and_duplicate_rejected(self):
        row = dict(stages=[dict(stage='投影', status='future_status')])
        self.assertEqual(gates(row)['投影'], 'unmeasured')
        row['stages'] *= 2
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            gates(row)

    def test_extra_failure_cannot_be_hidden_by_five_green_checks(self):
        plan = dict(motions=[dict(id='turn')], characters=[dict(id='a')])
        row = dict(cell='turn/a', readiness='needs_changes', stages=[
            dict(stage=s, status='sampled_pass') for s in STAGES])
        self.assertNotIn('可阶段复核', render(plan, [row]))
        row['readiness'] = 'stage_review'
        self.assertIn('可阶段复核', render(plan, [row]))
        self.assertIn('#cell-turn/a', render(plan, [row]))

    def test_counts_partition_each_gate(self):
        rows = [{}, dict(stages=[dict(stage='几何', status='needs_changes')])]
        self.assertEqual(coverage(rows)['几何'],
                         dict(sampled_pass=0, needs_changes=1, unmeasured=1))
        self.assertTrue(all(sum(c.values()) == 2 for c in coverage(rows).values()))
