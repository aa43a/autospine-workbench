"""Experimental pose entry preserves identity gates and interpolation probes."""
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.automation.motion_target_pose import PROFILE, final_times
from autospine_workbench.motion_validation import motion_ir_sha256
from test_motion_target_intake import inputs


class TargetPoseTests(unittest.TestCase):
    def test_corrective_progress_reaches_job_stage(self):
        from autospine_workbench.automation.motion_target_pose import correct
        stages=[]
        def repair(*args, **kwargs):
            kwargs['progress']({'iteration':0})
            return {}, {}
        with patch('autospine_workbench.targets.character43.projected_area_adaptive.build',side_effect=repair):
            correct({},'motion',{}, {'profile':PROFILE}, on_stage=stages.append)
        self.assertEqual(stages,['retarget'])

    def test_wrong_source_cannot_fall_back_to_rotation_candidate(self):
        with self.assertRaisesRegex(ValueError, 'identity_or_view_mismatch'):
            build_candidate(*inputs(), character_digest='a'*64, motion_digest='b'*64,
                            pose_fit=dict(profile=PROFILE, motion_sha256='0'*64))

    def test_unobservable_projection_cannot_fall_back(self):
        args=inputs()
        profile=dict(profile=PROFILE, motion_sha256=motion_ir_sha256(args[1]), vectors={}, times=[0,1])
        with patch('autospine_workbench.targets.character43.source_pose_fit.fit',
                   side_effect=ValueError('source_pose_unobservable')):
            with self.assertRaisesRegex(ValueError, 'unobservable'):
                build_candidate(*args, character_digest='a'*64, motion_digest='b'*64, pose_fit=profile)

    def test_near_camera_source_uncertainty_is_preserved_in_candidate_issues(self):
        import json
        args=inputs()
        row=dict(bone='forearm_r',unreliable_frames=[dict(frame=0,time=0,visibility=.02)])
        def projected(document,*unused,**kwargs):
            return document,dict(target_profile=PROFILE,records=[row])
        with patch('autospine_workbench.automation.motion_target_pose.project',side_effect=projected), \
             patch('autospine_workbench.automation.motion_target_pose.correct',side_effect=lambda doc,*a,**k:(doc,{})):
            files,evidence,_=build_candidate(*args,character_digest='a'*64,motion_digest='b'*64,
                                            pose_fit={'profile':PROFILE})
        issue=dict(stage='projection',reason_code='motion_source_pose_direction_unreliable')
        self.assertIn(issue,evidence['issues'])
        self.assertEqual(evidence['status'],'needs_changes')
        saved=json.loads(files['motion-review.json'])
        self.assertIn(issue,saved['issues'])
        self.assertEqual(saved['source_pose_fit']['records'],[row])

    def test_final_grid_covers_bone_deform_and_existing_contact_samples(self):
        doc={'animations':{'motion':{'bones':{'arm':{'rotate':[{'time':0},{'time':1}]}},
            'attachments':{'default':{'slot':{'mesh':{'deform':[{'time':0.3}]}}}}}}}
        times=final_times(doc,'motion',[0.6])
        self.assertEqual(times,[0,0.15,0.3,0.44999999999999996,0.6,0.8,1])


if __name__=='__main__':
    unittest.main()
