import json
from pathlib import Path
import unittest
from autospine_workbench.automation.character_binding_status import needs_review
from autospine_workbench.automation.character_cohort import summarize


class BindingStatusTests(unittest.TestCase):
    def test_action_matrix_shared_with_web(self):
        cases=json.loads((Path(__file__).parent/'fixtures/character-binding-status.json').read_bytes())
        for case in cases:
            with self.subTest(case=case['name']):
                self.assertEqual(needs_review(case['layer'],case['confirmed']),case['expected'])

    def test_edited_pending_is_not_completed_character(self):
        from tests.test_character_cohort import CohortTests
        c,o=CohortTests().fixture();o['a']=CohortTests().complete()
        o['a']['job']['layers'][0]['binding_decision'].update(action='pending',option_id=None)
        result=summarize(c,o)
        self.assertFalse(result['characters'][0]['completed'])
        self.assertEqual(result['characters'][0]['unresolved_layers'],['arm'])
