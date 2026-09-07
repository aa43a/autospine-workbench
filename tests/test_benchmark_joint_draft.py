"""Joint observations reject guessed authority and invalid geometric data."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from autospine_workbench.benchmark.joint_draft import build_joint_draft, validate_joint_draft


def candidate():
    return {"schema": "autospine.benchmark-semantic-candidates/v1", "authority": "none",
            "canvas": [200, 100], "coordinate_system": "psd_canvas"}


class JointDraftTests(unittest.TestCase):
    def test_blank_initial_observations_and_copy(self):
        source = candidate()
        draft = build_joint_draft(source)
        self.assertEqual(len(draft['records']), 17)
        self.assertTrue(all(r['status'] == 'unmarked' and r['position'] is None for r in draft['records']))
        checked = validate_joint_draft(source, draft)
        checked['records'][0]['notes'] = 'changed'
        self.assertEqual(draft['records'][0]['notes'], '')

    def test_observed_bounds_and_finite_values(self):
        draft = build_joint_draft(candidate())
        draft['records'][0].update(status='observed', position=[200, 0])
        self.assertEqual(validate_joint_draft(candidate(), draft), draft)
        for point in ([201, 0], [-1, 2], [1, float('nan')], [True, 2], [2], '2,3', [10**1000, 0]):
            with self.subTest(point=point), self.assertRaisesRegex(ValueError, 'benchmark_joint_position_invalid'):
                value = deepcopy(draft)
                value['records'][0]['position'] = point
                validate_joint_draft(candidate(), value)

    def test_unobservable_needs_reason_no_coordinate(self):
        draft = build_joint_draft(candidate())
        draft['records'][0]['status'] = 'unobservable'
        with self.assertRaisesRegex(ValueError, 'reason_required'):
            validate_joint_draft(candidate(), draft)
        draft['records'][0]['notes'] = '被裙摆遮挡'
        validate_joint_draft(candidate(), draft)
        draft['records'][0]['position'] = [0, 0]
        with self.assertRaisesRegex(ValueError, 'position_invalid'):
            validate_joint_draft(candidate(), draft)

    def test_identity_order_authority_and_notes(self):
        for mutation in (
            lambda d: d.update(candidate_sha256='0'*64), lambda d: d.update(authority='human'),
            lambda d: d['records'].reverse(), lambda d: d['records'][0].update(notes='a\x00'),
            lambda d: d['records'][0].update(notes='a'*1001),
            lambda d: d['records'][0].update(position=[0, 0]),
        ):
            draft = build_joint_draft(candidate())
            mutation(draft)
            with self.assertRaises(ValueError):
                validate_joint_draft(candidate(), draft)


if __name__ == '__main__':
    unittest.main()
