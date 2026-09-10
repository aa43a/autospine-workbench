import unittest
from autospine_workbench.automation.sleeve_admission_reason import blocking_reason


class SleeveAdmissionReasonTests(unittest.TestCase):
    def test_missing_or_empty_tracks_are_not_success_or_geometry_evidence(self):
        self.assertEqual(blocking_reason({'reason_codes': ['cloth_helper_unobservable']}), 'cloth_helper_unobservable')
        self.assertEqual(blocking_reason({'tracks': []}), 'motion_envelope_not_evaluated')
        self.assertEqual(blocking_reason({}), 'motion_envelope_not_evaluated')

    def test_actual_track_failure_and_sampled_success_remain_distinct(self):
        self.assertEqual(blocking_reason({'tracks': [{'failed_ticks': 1}]}), 'motion_envelope_geometry_failure')
        self.assertIsNone(blocking_reason({'tracks': [{'failed_ticks': 0}]}))
