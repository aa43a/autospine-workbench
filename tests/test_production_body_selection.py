"""A production repair must be a verified registration for its exact inputs."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.production_body_selection import select, validate
from autospine_workbench.automation.production_driver import ProductionDriver
import test_motion_joint_source as fixtures
from autospine_workbench.automation.storage_io import canonical_bytes


class ProductionBodyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.JointBodySourceTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.driver=ProductionDriver(self.f.manager)
        source=self.f.f.request
        self.request={k:source[k] for k in ('project_id','character_job_id','character_sha256','source_job_id')}
        self.request.update(source_sha256=source['source_job_sha256'],body_options={},joint_config={})

    def test_exact_registered_selection_and_tamper_rejection(self):
        selection=select(self.driver,self.request,self.f.job,self.f.registration)
        self.assertEqual(selection['artifact_sha256'],self.f.f.receipt['candidate_bundle_sha256'])
        self.assertNotEqual(selection['artifact_sha256'],self.f.main)
        request=dict(self.request,body_selection=selection);validate(self.driver,request)
        altered=deepcopy(request);altered['body_selection']['related_evidence_sha256']='0'*64
        with self.assertRaisesRegex(RuntimeError,'selection_changed'): validate(self.driver,altered)
        for key in ('project_id','character_sha256','source_job_id','source_sha256'):
            altered=dict(self.request,**{key:'wrong'})
            with self.subTest(key=key),self.assertRaisesRegex(RuntimeError,'source_mismatch'):
                select(self.driver,altered,self.f.job,self.f.registration)

    def test_changed_body_parameters_cannot_reuse_repair(self):
        with self.assertRaisesRegex(RuntimeError,'parameters_changed'):
            select(self.driver,dict(self.request,body_options={'projection':{'yaw':42}}),self.f.job,self.f.registration)

    def test_joint_dispatch_receives_selected_registration_not_baseline(self):
        selection=select(self.driver,self.request,self.f.job,self.f.registration)
        run=dict(request=dict(self.request,body_selection=selection),stages={'body':{'job_id':self.f.job}})
        meta=dict(artifact_sha256=selection['artifact_sha256'],source_provenance={k:v for k,v in selection.items() if k not in ('root_job_id','selector','lineage')})
        with patch('autospine_workbench.automation.motion_joint_jobs.inspect',return_value=meta) as inspect, \
             patch('autospine_workbench.automation.motion_joint_jobs.submit',return_value={}) as submit:
            self.driver.submit('joint',run,'motion-'+'f'*32)
            inspect.assert_called_once_with(self.f.manager,self.f.job,self.f.registration)
            self.assertEqual(submit.call_args.args[2]['registration_sha256'],self.f.registration)
            self.assertEqual(submit.call_args.args[2]['artifact_sha256'],selection['artifact_sha256'])

    def test_repair_job_must_trace_to_exact_root(self):
        job='motion-'+'e'*32
        folder=self.f.folder.parent/job;folder.mkdir()
        request=deepcopy(self.f.f.request)
        request.update(job_id=job,repair_execution=dict(parent_job_id=self.f.job,parent_artifact_sha256=self.f.main))
        (folder/'request.json').write_bytes(canonical_bytes(request))
        child=deepcopy(self.f.parent);child['result']['artifact_sha256']=self.f.f.receipt['candidate_bundle_sha256']
        self.f.manager.folder=lambda key:self.f.folder.parent/key
        self.f.manager.get=lambda key:deepcopy(child if key==job else self.f.parent)
        selected=select(self.driver,self.request,self.f.job,'job:'+job)
        self.assertEqual(selected['root_job_id'],self.f.job)
        self.assertEqual(selected['parent_job_id'],job)
        self.assertIsNone(selected['registration_sha256'])
        self.assertEqual(len(selected['lineage']),2)
        validate(self.driver,dict(self.request,body_selection=selected))
        run=dict(request=dict(self.request,body_selection=selected),stages={'body':{'job_id':self.f.job}})
        meta=dict(artifact_sha256=selected['artifact_sha256'],source_provenance={k:v for k,v in selected.items() if k not in ('root_job_id','selector','lineage')})
        with patch('autospine_workbench.automation.motion_joint_jobs.inspect',return_value=meta) as inspect, \
             patch('autospine_workbench.automation.motion_joint_jobs.submit',return_value={}) as submit:
            self.driver.submit('joint',run,'motion-'+'f'*32)
            inspect.assert_called_once_with(self.f.manager,job,None)
            self.assertNotIn('registration_sha256',submit.call_args.args[2])
        request['repair_execution']['parent_artifact_sha256']='wrong'
        (folder/'request.json').write_bytes(canonical_bytes(request))
        with self.assertRaisesRegex(RuntimeError,'lineage_changed'):
            validate(self.driver,dict(self.request,body_selection=selected))
        request.pop('repair_execution')
        (folder/'request.json').write_bytes(canonical_bytes(request))
        with self.assertRaisesRegex(RuntimeError,'unrelated_body'):
            select(self.driver,self.request,self.f.job,'job:'+job)
