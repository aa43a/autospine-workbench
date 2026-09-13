from copy import deepcopy
import unittest
from autospine_workbench.automation.cohort_workflow import summarize
import test_character_cohort as fixtures


class WorkflowTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(character_id=str(i), name=str(i), dataset_split='visible',
                     reason_code='source_matched_workflow_not_assessed',
                     exact_projects=[dict(id=str(i), lifecycle='active')]) for i in range(10)]
        return dict(schema='autospine.cohort-intake/v2', authority='none',
                    production_authorized=False, characters=rows), {str(i): {} for i in range(10)}

    def test_completed_candidate_keeps_ten_denominator_and_unknown_metrics(self):
        intake, observations = self.fixture()
        observations['0'] = fixtures.CohortTests().complete()
        report = summarize(intake, observations)
        self.assertEqual(report['metrics']['completed_characters'], 1)
        self.assertEqual(report['metrics']['completion_rate'], .1)
        self.assertEqual(report['metrics']['required_motion_cases'], 30)
        self.assertEqual(report['metrics']['runtime_passed_motion_cases'], 3)
        self.assertIsNone(report['metrics']['human_review_minutes'])
        self.assertIsNone(report['metrics']['incorrect_auto_adoption_rate'])

    def test_source_ambiguity_never_borrows_a_green_project(self):
        intake, observations = self.fixture()
        intake['characters'][0]['reason_code'] = 'psd_variant_review_required'
        observations.pop('0')
        row = summarize(intake, observations)['characters'][0]
        self.assertFalse(row['completed'])
        self.assertIsNone(row['project_id'])
        self.assertIn('psd_variant_review_required', row['reason_codes'])
        observations['0'] = fixtures.CohortTests().complete()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            summarize(intake, observations)

    def test_missing_and_stale_binding_evidence_remains_incomplete(self):
        intake, observations = self.fixture()
        observations['0'] = fixtures.CohortTests().complete()
        observations['0']['job']['layers'][0]['binding_decision'].update(
            decision_source='policy_auto', evidence_current=False)
        before = deepcopy(observations)
        result = summarize(intake, observations)
        self.assertEqual(result['metrics']['completed_characters'], 0)
        self.assertIn('automatic_binding_evidence_stale', result['characters'][0]['reason_codes'])
        self.assertEqual(observations, before)

    def test_same_project_cannot_count_as_two_characters(self):
        intake, observations = self.fixture()
        intake['characters'][1]['exact_projects'][0]['id'] = '0'
        observations.pop('1')
        with self.assertRaisesRegex(ValueError, 'duplicate_project'):
            summarize(intake, observations)
