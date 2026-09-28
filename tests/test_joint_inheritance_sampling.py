import json
import unittest

from autospine_workbench.automation.motion_joint_inheritance import review
from autospine_workbench.targets.character43.joint_sampling import preflight


class InheritanceSamplingTests(unittest.TestCase):
    def test_related_review_cannot_borrow_main_source_pass_flags(self):
        document = {'bones': [{'name': n, 'x': 0, 'y': 10}
                             for n in ('calf_l', 'foot_l', 'calf_r', 'foot_r')]}
        source = dict(files={'skeleton.json': json.dumps(document).encode()}, artifact_sha256='a'*64,
                      related=dict(candidate_sha256='a'*64, evidence={'limitations': ['visual_missing']}, receipt={}))
        result = review(source)
        self.assertEqual(result['reference_length_px'], 20)
        self.assertIsNone(result['geometry_passed'])
        self.assertEqual(result['depth_order_status'], 'unmeasured')
        self.assertEqual(result['related_evidence']['limitations'], ['visual_missing'])
        self.assertTrue(result['issues'])
        source['related']['candidate_sha256'] = 'b'*64
        with self.assertRaisesRegex(ValueError, 'related_evidence_required'): review(source)

    def test_long_clip_and_dense_existing_probes_rejected_without_removing_probes(self):
        self.assertTrue(preflight([0, 19.966667])['supported'])
        self.assertFalse(preflight([0, 60])['supported'])
        self.assertFalse(preflight([i/1000 for i in range(4097)])['supported'])


if __name__ == '__main__': unittest.main()
