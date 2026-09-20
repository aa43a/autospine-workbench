from copy import deepcopy
import unittest

from autospine_workbench.automation.cohort_metric_display import render


class MetricDisplayTests(unittest.TestCase):
    def test_missing_measurements_are_not_zero(self):
        page = render({'runtime_failure_rate': None})
        self.assertIn('Runtime 失败率：未测量', page)
        self.assertNotIn('0%', page)
        self.assertIn('人工总耗时：未测量', page)

    def test_partial_measurements_and_default_assignments_keep_distinct_scopes(self):
        metrics = dict(runtime_failure_rate=0, auto_binding_audit=dict(
            assessed_bindings=12, eligible_bindings=119, incorrect=0, unobservable=0,
            not_reviewed=107, sampled_error_rate=0,
            audit_timing=dict(measured_projects=1, total_projects=10, measured_minutes=1.4)),
            project_work_timing=dict(recorded_minutes=2, measured_projects=1, total_projects=10))
        original = deepcopy(metrics)
        page = render(metrics)
        self.assertIn('默认沿用且未单独抽查 107 项', page)
        self.assertIn('明确判断 12/119 项', page)
        self.assertIn('Runtime 失败率：0%', page)
        self.assertIn('不包含全部历史构建或重试', page)
        self.assertIn('已记录项目操作耗时：2 分钟', page)
        self.assertIn('不与视觉或抽查计时相加', page)
        self.assertIn('人工总耗时：未测量', page)
        self.assertEqual(metrics, original)

    def test_zero_recorded_minutes_remains_measured(self):
        page = render(dict(project_work_timing=dict(recorded_minutes=0, measured_projects=1, total_projects=10)))
        self.assertIn('已记录项目操作耗时：0 分钟', page)
        page = render(dict(project_work_timing=dict(recorded_minutes=None, measured_projects=0, total_projects=10)))
        self.assertIn('已记录项目操作耗时：未测量', page)
