from copy import deepcopy
from hashlib import sha256
import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_post_contact import apply, PROFILE, TIMELINE_PROFILE
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_pose_policy import select, prepare, HIP_PROFILE
from autospine_workbench.automation.pipeline_run import PipelineRunError


class PostContactTests(unittest.TestCase):
    def test_new_profile_survives_preparation(self):
        with patch('autospine_workbench.automation.motion_target_pose.prepare',return_value={'profile':HIP_PROFILE}), \
             patch('autospine_workbench.targets.character43.source_foot_orientation.extract',return_value={'times':[0,1]}):
            pose=prepare(object(),dict(pose_profile=TIMELINE_PROFILE))
        self.assertEqual(pose['post_contact_profile'],TIMELINE_PROFILE)

    def test_prepares_foot_observations_from_same_verified_bundle(self):
        bundle=object()
        with patch('autospine_workbench.automation.motion_target_pose.prepare',return_value={'profile':HIP_PROFILE}) as base, \
             patch('autospine_workbench.targets.character43.source_foot_orientation.extract',return_value={'times':[0,1]}) as foot:
            pose=prepare(bundle,dict(pose_profile=PROFILE))
        base.assert_called_once_with(bundle,hip_center=True)
        foot.assert_called_once_with(bundle)
        self.assertEqual(pose['profile'],HIP_PROFILE)
        self.assertEqual(pose['post_contact_profile'],PROFILE)
        self.assertEqual(pose['foot_observations']['times'],[0,1])

    def test_repair_progress_roundtrips_through_job_protocol(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from autospine_workbench.automation.motion_intake_process import progress, read_progress
        with TemporaryDirectory() as folder:
            progress(Path(folder),'post_contact_repair')
            self.assertEqual(read_progress(Path(folder)),'post_contact_repair')

    def test_strategy_requires_contact_and_rejects_incompatible_views(self):
        for profile in (PROFILE,TIMELINE_PROFILE):
            self.assertEqual(select(dict(pose_profile=profile)), profile)
            for extra in ({'contact_correction':False}, {'inferred_contact_profile':None}, {'clip':{}}):
                with self.assertRaises(PipelineRunError): select(dict(pose_profile=profile, **extra))

    def test_replay_precedes_repair_and_failures_are_not_hidden(self):
        names=('thigh_l','calf_l','thigh_r','calf_r')
        tracks={n:{'rotate':[dict(time=0,value=10),dict(time=1,value=20)]} for n in names}
        tracks['root']={'translate':[dict(time=0,x=0,y=0),dict(time=1,x=3,y=4)]}
        doc={'bones':[], 'animations':{'a':{'bones':tracks}}}
        contact=dict(selected=False,status='inferred_proxy_drift',
            input_skeleton_sha256=sha256(canonical_bytes(doc)).hexdigest(),
            hypothesis=dict(ticks_per_second=100,markers=[dict(kind='contact', limb='leg.left', start_tick=0, end_tick=100)]),
            phase_attempt=dict(status='candidate',profile='causal-joint-support-timeline-v1',
                rows=[dict(time=t,root_shift=[2,1],angles={n:5 for n in names}) for t in (0,1)]))
        original=deepcopy((doc,contact))
        evidence=dict(area_repair={'records':[]},reference_length_px=100)
        pose=dict(post_contact_profile=PROFILE,foot_observations={'observed':True})
        def repair(d,*args,**kwargs):
            self.assertEqual(d['animations']['a']['bones']['root']['translate'][-1]['x'],5)
            self.assertTrue(kwargs['fixed_band']);self.assertTrue(kwargs['interpolation_margin'])
            return d,dict(refinement=[{'check':{'failures':[{'time':.5}]}}])
        with patch('autospine_workbench.targets.character43.foot_orientation_fit.fit',side_effect=lambda d,*_,**kw: (d,{})) as foot, \
             patch('autospine_workbench.targets.character43.projected_area_adaptive.build',side_effect=repair), \
             patch('autospine_workbench.targets.character43.motion_contacts.analyze',return_value={'passed':True}) as check:
            for profile in (PROFILE,TIMELINE_PROFILE):
                pose['post_contact_profile']=profile
                result, report, times, issues=apply(doc,'a',dict(ticks_per_second=100, duration_ticks=100, markers=[]),[],evidence,contact,[0,1],pose)
                self.assertEqual(foot.call_args.kwargs['temporal'],profile==TIMELINE_PROFILE)
                self.assertEqual(report['post_contact_profile'],profile)
        self.assertEqual((doc,contact),original)
        self.assertEqual(report['post_contact_before'],contact)
        self.assertEqual(report['status'],'inferred_proxy_corrected')
        self.assertEqual(issues[0]['reason_code'],'motion_post_contact_constraints_failed')
        self.assertEqual(times,[0,.5,1])
        self.assertEqual(check.call_args.args[2]['markers'],contact['hypothesis']['markers'])
        self.assertEqual(report['output_skeleton_sha256'],sha256(canonical_bytes(result)).hexdigest())

    def test_unowned_deform_cannot_be_removed(self):
        document={'animations':{'a':{'bones':{},'attachments':{'default':{'user':{}}}}}}
        with self.assertRaisesRegex(ValueError,'inventory_mismatch'):
            apply(document,'a',{},[],dict(area_repair={'records':[]}),{},[0,1],
                  dict(post_contact_profile=PROFILE))
