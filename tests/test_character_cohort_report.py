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

    def test_partial_session_metrics_do_not_claim_total_labor_or_population_accuracy(self):
        metrics=dict(completed_characters=3,total_characters=3,runtime_passed_motion_cases=9,required_motion_cases=9,
            auto_binding_audit=dict(assessed_bindings=10,eligible_bindings=30,incorrect=1,sampled_error_rate=.1,
                audit_timing=dict(measured_projects=1,total_projects=3,measured_minutes=2)),
            visual_review_timing=dict(measured_characters=0,total_characters=3,measured_minutes=None))
        html=render(dict(characters=[],metrics=metrics)).decode()
        self.assertIn('明确判断 10/30',html);self.assertIn('样本错误率 10.0%',html)
        self.assertIn('自动绑定抽查会话计时：1/3',html)
        self.assertIn('已测部分 2 分钟',html)
        self.assertIn('已测部分 未测量',html)
        self.assertIn('人工总耗时：未测量',html)
