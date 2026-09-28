from copy import deepcopy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from autospine_workbench.automation.motion_camera_policy import PROFILE,ANKLE_PROFILE,select
from autospine_workbench.automation.motion_pose_policy import prepare_inputs
from autospine_workbench.automation.motion_ankle_policy import prepare as prepare_ankles


def request():
    return dict(pose_profile=PROFILE,moving_ankle_profile=ANKLE_PROFILE,contact_correction=False,
                projection=dict(profile=PROFILE,keys=[dict(time=0,yaw=0),dict(time=2,yaw=360)]))


class CameraPolicyTests(unittest.TestCase):
    def test_projected_version_is_explicit_and_preserved(self):
        from autospine_workbench.targets.character43.projected_camera_sampling import PROFILE as PROJECTED
        body=request();body['projection']['sampling_profile']=PROJECTED;before=deepcopy(body)
        self.assertEqual(select(body,2),PROFILE);self.assertEqual(body,before)
    def test_profiles_and_complete_track_are_required(self):
        self.assertEqual(select(request(),2),PROFILE)
        for change in ({'contact_correction':True},{'moving_ankle_profile':'moving-source-ankle-timeline-v1'},
                       {'pose_profile':None},{'clip':{}},{'torso_projection_profile':'other'},
                       {'projection_selection':{}},{'depth_review_profile':'external-regional-depth-order-v1'}):
            with self.assertRaises(Exception):select(dict(request(),**change),2)
        with self.assertRaisesRegex(Exception,'key_invalid'):select(request(),1)

    def test_invalid_tracks_are_rejected_without_coercion(self):
        for keys in (None,[],[dict(time=0,yaw=True)],[dict(time=0,yaw=float('nan'))],
                     [dict(time=0,yaw=0),dict(time=0,yaw=360)]):
            body=request();body['projection']['keys']=keys
            with self.assertRaises(Exception):select(body,2)

    def test_pose_and_ankles_receive_the_same_full_track(self):
        body=request();before=deepcopy(body);bundle=SimpleNamespace(motion=dict(duration_ticks=2000000,ticks_per_second=1000000))
        with patch('autospine_workbench.automation.motion_camera_pose.prepare',return_value=('motion','receipt','pose')) as pose:
            self.assertEqual(prepare_inputs(bundle,body),('motion','receipt','pose'))
            pose.assert_called_once_with(bundle,body['projection']['keys'],sampling_profile=None)
        with patch('autospine_workbench.targets.character43.camera_ankle_targets.extract',return_value='ankles') as ankles:
            self.assertEqual(prepare_ankles(bundle,body),'ankles')
            ankles.assert_called_once_with(bundle,body['projection']['keys'],sampling_profile=None)
        self.assertEqual(body,before)

    def test_explicit_sampling_version_reaches_pose_and_ankles(self):
        from autospine_workbench.targets.character43.camera_sampling import PROFILE as SAMPLING
        body=request();body['projection']['sampling_profile']=SAMPLING
        bundle=SimpleNamespace(motion=dict(duration_ticks=2000000,ticks_per_second=1000000))
        with patch('autospine_workbench.automation.motion_camera_pose.prepare',return_value=(1,2,3)) as pose:
            prepare_inputs(bundle,body);self.assertEqual(pose.call_args.kwargs['sampling_profile'],SAMPLING)
        with patch('autospine_workbench.targets.character43.camera_ankle_targets.extract') as ankles:
            prepare_ankles(bundle,body);self.assertEqual(ankles.call_args.kwargs['sampling_profile'],SAMPLING)
        body['projection']['sampling_profile']='future'
        with self.assertRaisesRegex(Exception,'unsupported'):select(body,2)
