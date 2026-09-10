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
