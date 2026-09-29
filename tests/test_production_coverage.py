from unittest import TestCase
from autospine_workbench.automation.production_coverage import summarize


class CoverageTests(TestCase):
    def test_successful_build_does_not_hide_static_or_missing_regions(self):
        value = summarize(dict(status='needs_review', layers=[
            dict(layer_id='hair', state='static_reference', regions=[]),
            dict(layer_id='arm', state='weighted_candidate', regions=[dict(region_id='a', state='weighted_candidate')]),
            dict(layer_id='shoe', state='weighted_candidate', missing_region_ids=['edge']),
            dict(layer_id='mixed', state='weighted_candidate', regions=[dict(region_id='b', state='static_reference')])]))
        self.assertEqual(value['unresolved_layer_count'], 3)
        self.assertEqual(value['layer_count'], 4)
        self.assertNotIn('accepted', value)
