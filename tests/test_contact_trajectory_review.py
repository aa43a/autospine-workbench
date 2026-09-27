import json
import unittest

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.contact_trajectory_review import render


class ContactTrajectoryReviewTests(unittest.TestCase):
    def files(self):
        identity = canonical_sha256({})
        moving = dict(applied=True, final_check=dict(skeleton_sha256=identity), trajectory=[
            dict(time=0, targets=[[0, 0], [10, 0]]),
            dict(time=2, targets=[[0, 0], [14, 0]])])
        contact = dict(status='inferred_proxy_drift',
                       final_timeline_check=dict(skeleton_sha256=identity),
                       after=dict(intervals=[dict(limb='leg.right', start=1, end=2,
                           max_drift_px=1, samples=[dict(time=1, x=12, y=0),
                                                   dict(time=1.5, x=13, y=0)])]))
        return {k: json.dumps(v).encode() for k, v in {
            'skeleton.json': {}, 'motion-moving-ankles.json': moving,
            'motion-contact.json': contact}.items()}

    def test_interpolates_at_contact_samples_relative_to_interval_start(self):
        files = self.files()
        original = dict(files)
        html = render(files)
        self.assertIn('<td>1.000 px</td><td>1.000 px</td><td>0.000000 px</td>', html)
        self.assertIn('不会清除接触异常', html)
        self.assertEqual(files, original)

    def test_stale_final_contact_cannot_explain_current_motion(self):
        files = self.files()
        contact = json.loads(files['motion-contact.json'])
        contact['final_timeline_check']['skeleton_sha256'] = '0'*64
        files['motion-contact.json'] = json.dumps(contact).encode()
        self.assertIn('缺少匹配的最终检查', render(files))
        self.assertNotIn('<table>', render(files))

    def test_absent_moving_profile_keeps_legacy_page(self):
        self.assertEqual(render({}), '')
