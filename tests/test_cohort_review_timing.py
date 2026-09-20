from copy import deepcopy
import unittest

from autospine_workbench.automation.cohort_workflow import summarize
from autospine_workbench.automation.cohort_workflow_report import render
from autospine_workbench.automation.character_cohort import summarize as fixed_summary
from test_cohort_workflow import WorkflowTests
from test_character_cohort import CohortTests


class ReviewTimingTests(unittest.TestCase):
    def timed(self, seconds):
        row = CohortTests().complete()
        row['visual_review']['timing'] = dict(method='operator_stopwatch_v1',
            scope='whole_character_visual_review_session', seconds=seconds)
        return row

    def test_partial_timing_and_zero_are_distinct_from_missing(self):
        intake, observations = WorkflowTests().fixture()
        observations.update({'0': self.timed(90), '1': self.timed(0)})
        before = deepcopy(observations)
        result = summarize(intake, observations)
        timing = result['metrics']['visual_review_timing']
        self.assertEqual(timing['measured_characters'], 2)
        self.assertEqual(timing['measured_minutes'], 1.5)
        self.assertEqual(timing['unmeasured_character_ids'], [str(i) for i in range(2, 10)])
        self.assertFalse(timing['all_characters_measured'])
        self.assertIsNone(result['metrics']['human_review_minutes'])
        self.assertIn('2/10 名角色', render(result, 'http://localhost:8918'))
        self.assertIn('已测部分合计 1.5 分钟', render(result, 'http://localhost:8918'))
        self.assertEqual(observations, before)

    def test_invalid_or_absent_measurement_is_not_zero(self):
        intake, observations = WorkflowTests().fixture()
        for value in (True, -1, float('nan'), float('inf'), 86401):
            observations['0'] = self.timed(value)
            timing = summarize(intake, observations)['metrics']['visual_review_timing']
            self.assertEqual(timing['measured_characters'], 0)
            self.assertIsNone(timing['measured_minutes'])

    def test_complete_fixed_cohort_timing_is_still_not_all_labor(self):
        cohort, _ = CohortTests().fixture()
        result = fixed_summary(cohort, {p: self.timed(60) for p in ('a', 'b', 'c')})
        timing = result['metrics']['visual_review_timing']
        self.assertTrue(timing['all_characters_measured'])
        self.assertEqual(timing['measured_minutes'], 3)
        self.assertEqual(timing['unmeasured_character_ids'], [])
        self.assertIsNone(result['metrics']['human_review_minutes'])

    def test_legacy_snapshots_remain_renderable(self):
        intake, observations = WorkflowTests().fixture()
        report = summarize(intake, observations)
        report['metrics'].pop('visual_review_timing')
        self.assertIn('人工总耗时：未测量', render(report, 'http://localhost:8918'))
