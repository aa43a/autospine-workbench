import unittest

from autospine_workbench.automation.sleeve_workflow_review import render


class SleeveWorkflowReviewTests(unittest.TestCase):
    def test_review_links_to_latest_completed_geometry(self):
        report = dict(project_id='fixture', records=[], runtime_status='not_evaluated',
                      steps=[dict(id='cuff', status='succeeded', cached=False)])
        self.assertIn('href="cuff/fixture/index.html"', render(report))
        report['steps'].append(dict(id='repair', status='failed', cached=False))
        self.assertIn('href="cuff/fixture/index.html"', render(report))
        report['steps'][-1]['status'] = 'succeeded'
        self.assertIn('href="repair/fixture/index.html"', render(report))
        self.assertNotIn('href="cuff/fixture/index.html"', render(report))

    def test_ordinary_comparison_is_source_scoped_and_keeps_blocked_results(self):
        report=dict(project_id='fixture', records=[], runtime_status='not_evaluated',
                    ordinary_review='ordinary-deform/fixture/index.html',
                    steps=[dict(id='ordinary-deform',status='succeeded',cached=False)])
        page=render(report)
        self.assertIn('修正普通袖局部变形',page)
        self.assertIn('普通袖修正前后同步对比',page)
        self.assertNotIn('boundary/fixture',page)
        report['ordinary_review']='ordinary-deform/other/index.html'
        self.assertNotIn('同步对比',render(report))
        report['ordinary_review']='ordinary-deform/fixture/index.html'
        report['steps'][0]['status']='failed'
        self.assertNotIn('同步对比',render(report))
        self.assertNotIn('修正普通袖局部变形✓',render(report))
