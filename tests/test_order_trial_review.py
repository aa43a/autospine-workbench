import unittest
from m4_order_trial_review import assess


class OrderTrialTests(unittest.TestCase):
    def test_unknown_crossed_garment_prevents_compatible_claim(self):
        order = ['hand','inner','leg','front']
        row = dict(time=.5, region='hand', body='front', counterfactual=dict(after_slot='leg',
            restored_full_frame=True, selected=False, order=['inner','leg','hand','front'],
            crossed_slots=['inner','leg'], full_frame_changed_pixels=100, full_frame_alpha_changes=0, selected_pixel_changes=2))
        checks = [dict(arm='hand',body='leg',time=.5,status='uniform_front_proxy')]
        self.assertEqual(assess(row,order,checks)['status'], 'unresolved_crossed_surface')
        checks.append(dict(arm='hand',body='inner',time=.5,status='no_overlap'))
        self.assertEqual(assess(row,order,checks)['status'], 'sample_proxy_compatible')
        row['counterfactual']['crossed_slots'] = ['leg']
        with self.assertRaisesRegex(ValueError,'unreported'): assess(row,order,checks)

    def test_changed_front_cover_or_unrestored_frame_rejected(self):
        row = dict(time=.5,region='hand',body='front',counterfactual=dict(after_slot='leg',
            restored_full_frame=True,selected=False,order=['front','leg','hand'],crossed_slots=['front','leg']))
        with self.assertRaisesRegex(ValueError,'front_cover'): assess(row,['hand','front','leg'],[])
        row['counterfactual']['restored_full_frame'] = False
        with self.assertRaisesRegex(ValueError,'unrestored'): assess(row,['hand','front','leg'],[])
