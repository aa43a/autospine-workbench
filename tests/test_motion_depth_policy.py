import unittest
from autospine_workbench.automation.motion_depth_policy import select, LEGACY, OVERLAP_PROFILE, REGIONAL
from autospine_workbench.automation.pipeline_run import PipelineRunError


class DepthPolicyTests(unittest.TestCase):
    def test_default_and_explicit_historical_profiles(self):
        for format in ('fbx', 'bvh', 'npz'):
            self.assertEqual(select({}, dict(format=format)), OVERLAP_PROFILE)
            for profile in (LEGACY, OVERLAP_PROFILE):
                self.assertEqual(select(dict(depth_review_profile=profile), dict(format=format)), profile)

    def test_regional_requires_supported_source(self):
        for format in ('fbx', 'bvh'):
            self.assertEqual(select(dict(depth_review_profile=REGIONAL), dict(format=format)), REGIONAL)
        for format in ('npz', None):
            with self.assertRaisesRegex(PipelineRunError, 'bvh_required'):
                select(dict(depth_review_profile=REGIONAL), dict(format=format))

    def test_unknown_profile_rejected(self):
        for value in (None, {}, [], 1, 'automatic'):
            with self.assertRaisesRegex(PipelineRunError, 'unsupported'):
                select(dict(depth_review_profile=value), dict(format='bvh'))
