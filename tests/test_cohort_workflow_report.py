from copy import deepcopy
import unittest

from autospine_workbench.automation.cohort_workflow import summarize
from autospine_workbench.automation.cohort_workflow_report import render
import test_cohort_workflow as workflow_fixtures
import test_character_cohort as cohort_fixtures


class WorkflowReportTests(unittest.TestCase):
    def test_runtime_success_does_not_hide_binding_or_visual_work(self):
        intake, observations = workflow_fixtures.WorkflowTests().fixture()
        observed = cohort_fixtures.CohortTests().complete()
        observed['job'].update(job_id='job-a', artifact_sha256='a' * 64)
        observed['job']['layers'][0]['state'] = 'static_reference'
        observed['visual_review']['aspects']['motion'] = 'not_reviewed'
        observations['0'] = observed
        report = summarize(intake, observations)
        before = deepcopy(report)
        page = render(report, 'http://127.0.0.1:8918')
        self.assertIn('整角色完成 0/10', page)
        self.assertIn('必需动作验证 3/30', page)
        self.assertIn('待处理 1 层', page)
        self.assertIn('待复核', page)
        self.assertIn('/jobs/job-a/view/index.html', page)
        self.assertIn('尚无图层库存', page)
        self.assertIn('不会自动刷新', page)
        self.assertEqual(report, before)

    def test_unselected_source_has_no_candidate_link_and_names_are_escaped(self):
        intake, observations = workflow_fixtures.WorkflowTests().fixture()
        intake['characters'][0].update(name='<img src=x>', reason_code='psd_variant_review_required')
        observations.pop('0')
        report = summarize(intake, observations)
        page = render(report, 'http://localhost:8918')
        self.assertIn('&lt;img src=x&gt;', page)
        self.assertNotIn('<img src=x>', page)
        self.assertNotIn('/jobs/', page)
        self.assertIn('需要选择 PSD 版本', page)
        self.assertIn('人工总耗时：未测量', page)

    def test_external_or_injected_origins_are_rejected(self):
        intake, observations = workflow_fixtures.WorkflowTests().fixture()
        report = summarize(intake, observations)
        for origin in ['https://example.com', 'http://localhost/?x="', 'http://user@localhost']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                render(report, origin)

    def test_exception_details_preserve_names_reasons_and_escape_content(self):
        intake, observations = workflow_fixtures.WorkflowTests().fixture()
        observed = cohort_fixtures.CohortTests().complete()
        layer = observed['job']['layers'][0]
        layer.update(state='static_reference', name='<wing>',
                     reason_codes=['static_reference_not_bound'],
                     regions=[dict(region_id='<region>',state='static_reference')])
        observations['0'] = observed
        report = summarize(intake, observations)
        details = report['characters'][0]['unresolved_layer_details']
        self.assertEqual(details[0]['name'], '<wing>')
        page = render(report, 'http://localhost:8918')
        self.assertIn('&lt;wing&gt;',page)
        self.assertIn('仅保留静态参考，尚未绑定',page)
        self.assertIn('&lt;region&gt;',page)
        self.assertNotIn('<wing>',page)
        # Historical snapshots without the optional details remain readable.
        report['characters'][0].pop('unresolved_layer_details')
        self.assertIn(layer['layer_id'],render(report,'http://localhost:8918'))
