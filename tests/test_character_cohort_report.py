import unittest
from autospine_workbench.automation.character_cohort_report import render


class CohortReportTests(unittest.TestCase):
    def test_matrix_keeps_completion_and_motion_success_separate(self):
        row=dict(name='<actor>',motions=[dict(status='passed',sampled_frames=10)]*3,
                 unresolved_layers=['cloth'],visual_accepted=False,completed=False)
        html=render(dict(characters=[row],metrics=dict(completed_characters=0,total_characters=1,
                          runtime_passed_motion_cases=3,required_motion_cases=3))).decode()
        self.assertIn('整角色完成 0/1',html);self.assertIn('通过 3/3',html)
        self.assertIn('&lt;actor&gt;',html);self.assertIn('待复核',html)
        self.assertIn('错误自动采用率：未测量',html)
