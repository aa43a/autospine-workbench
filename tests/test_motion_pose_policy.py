import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_pose_policy import select,prepare,HIP_PROFILE
from autospine_workbench.automation.motion_target_comparison import signature


class MotionPosePolicyTests(unittest.TestCase):
    def test_legacy_and_conflicting_views(self):
        self.assertIsNone(select({}))
        self.assertEqual(select({'pose_profile':HIP_PROFILE}),HIP_PROFILE)
        for field in ('clip','projection','projection_selection','torso_projection_profile'):
            with self.assertRaisesRegex(Exception,'requires_full_original_view'):
                select({'pose_profile':HIP_PROFILE,field:{}})
        for value in (None,True,'unknown'):
            with self.assertRaisesRegex(Exception,'unsupported'):select({'pose_profile':value})

    def test_preparation_is_explicit_and_bound_to_verified_bundle(self):
        bundle=object()
        with patch('autospine_workbench.automation.motion_target_pose.prepare',return_value={'ready':True}) as build:
            self.assertIsNone(prepare(bundle,{}));build.assert_not_called()
            self.assertEqual(prepare(bundle,{'pose_profile':HIP_PROFILE}),{'ready':True})
            build.assert_called_once_with(bundle,hip_center=True)

    def test_view_comparison_never_mixes_pose_strategies(self):
        from types import SimpleNamespace
        manager=SimpleNamespace(get=lambda _:dict(source_sha256='a',format='bvh'))
        old=signature(manager,{'source_job_id':'source'})
        new=signature(manager,{'source_job_id':'source','pose_profile':HIP_PROFILE})
        self.assertNotIn('pose_profile',old)
        self.assertNotEqual(old,new)
