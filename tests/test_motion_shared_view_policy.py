from copy import deepcopy
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_pose_policy import select, prepare_inputs, VIEW_PROFILE
from autospine_workbench.automation.motion_view_pose import validate
from tests.test_motion_view_pose import ViewPoseTests


class SharedViewPolicyTests(unittest.TestCase):
    def request(self):
        return dict(pose_profile=VIEW_PROFILE, projection=dict(
            profile='constant-yaw-source-motion-v1', yaw_degrees=45))

    def test_requires_explicit_camera_and_full_timebase(self):
        self.assertEqual(select(self.request()),VIEW_PROFILE)
        for change in ({'projection':None}, {'projection':{}}, {'clip':{}},
                       {'projection':{'profile':'constant-yaw-source-motion-v1','yaw_degrees':91}}):
            with self.assertRaises(Exception): select(dict(self.request(),**change))

    def test_one_compile_snapshot_includes_selection_identity(self):
        prepared,_,_=ViewPoseTests().prepared(45)
        before=deepcopy(prepared);bundle=object()
        request=dict(self.request(),projection_selection={'comparison_sha256':'a'*64})
        with patch('autospine_workbench.automation.motion_view_pose.prepare',return_value=deepcopy(prepared)) as shared, \
             patch('autospine_workbench.targets.character43.oblique_target.prepare') as separate:
            motion,view,pose=prepare_inputs(bundle,request)
            shared.assert_called_once_with(bundle,45);separate.assert_not_called()
        validate(pose,motion,view,None)
        self.assertEqual(view['selection'],request['projection_selection'])
        self.assertEqual(prepared,before)
        wrong=deepcopy(view);wrong['selection']['comparison_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'identity_or_camera'):
            validate(pose,motion,wrong,None)

    def test_legacy_projection_path_remains_separate_without_pose(self):
        from types import SimpleNamespace
        bundle=SimpleNamespace(motion={'legacy':True})
        with patch('autospine_workbench.targets.character43.oblique_target.prepare',return_value=({'motion':True},{'view':True})):
            self.assertEqual(prepare_inputs(bundle,{'projection':self.request()['projection']}),
                             ({'motion':True},{'view':True},None))
