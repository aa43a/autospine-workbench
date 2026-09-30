from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
import time

from autospine_workbench.automation.production_entrance import ProductionEntrances
from autospine_workbench.automation.storage_io import canonical_bytes


class EntranceTests(TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        self.psd=dict(job_id='import-test',status='running')
        self.motion=dict(job_id='motion-test',kind='generate',status='running')
        for name,request in [('psd',dict(name='new.psd',source_sha256='psd')),
                             ('motion',dict(kind='generate',generation=dict(prompt='Breathe.')))]:
            folder=self.root/name;folder.mkdir();(folder/'request.json').write_bytes(canonical_bytes(request))
        imports=SimpleNamespace(root=self.root/'psd',folder=lambda job:self.root/'psd',get=lambda job:deepcopy(self.psd))
        projects=SimpleNamespace(get_project=lambda project:dict(resolved=dict(sha256='project-sha')))
        motions=SimpleNamespace(folder=lambda job:self.root/'motion',get=lambda job:deepcopy(self.motion),
            projects=projects,character_manager=lambda:SimpleNamespace(motion_target=lambda project:dict(job=None)))
        self.calls={}
        def ensure(request,run):
            if run in self.calls:self.assertEqual(self.calls[run],request)
            self.calls[run]=request
            return dict(status='pending')
        driver=SimpleNamespace(motions=motions,freeze=lambda body:dict(body,character_sha256=None))
        self.production=SimpleNamespace(journal=SimpleNamespace(root=self.root/'jobs/production'),driver=driver,ensure_reserved=ensure,list=lambda:[])
        self.manager=ProductionEntrances(self.production,imports,poll_seconds=.01)
        self.body=dict(character=dict(import_job_id='import-test'),source_job_id='motion-test',body_options={},joint_config={})

    def tearDown(self):
        self.manager.close();self.tmp.cleanup()

    def wait(self,job,status):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=self.manager.get(job)
            if result['status']==status:return result
            time.sleep(.01)
        self.fail(str(self.manager.get(job)))

    def test_pending_sources_survive_restart_then_link_one_reserved_run(self):
        created=self.manager.submit(self.body);job=created['job_id']
        self.wait(job,'running');self.assertEqual(self.calls,{})
        self.manager.close()
        self.psd.update(status='succeeded',project_id='new-project')
        self.motion.update(status='succeeded',result=dict(motion_status='compiled'))
        self.manager=ProductionEntrances(self.production,self.manager.imports,poll_seconds=.01)
        before=self.manager.get(job);self.manager.resume(job,before['revision'])
        ready=self.wait(job,'linked')
        self.assertEqual(ready['run_id'],created['run_id'])
        self.assertEqual(self.calls[ready['run_id']]['project_id'],'new-project')
        self.assertEqual(self.manager.submit(self.body)['job_id'],job)
        time.sleep(.03);self.assertEqual(len(self.calls),1)
        self.assertFalse(ready['production_authorized'])

    def test_character_recipe_survives_pending_source_restart_and_handoff(self):
        from autospine_workbench.automation.production_character_options import SKIRT_PROFILES
        body=dict(self.body,character_options=dict(skirt_profile=SKIRT_PROFILES[2]))
        created=self.manager.submit(body);job=created['job_id']
        self.wait(job,'running');self.manager.close()
        self.psd.update(status='succeeded',project_id='new-project')
        self.motion.update(status='succeeded',result=dict(motion_status='compiled'))
        self.manager=ProductionEntrances(self.production,self.manager.imports,poll_seconds=.01)
        self.manager.resume(job,self.manager.get(job)['revision'])
        ready=self.wait(job,'linked')
        request=self.calls[ready['run_id']]
        self.assertEqual(request['character_options'],body['character_options'])
        body['character_options']['skirt_profile']=None
        self.assertEqual(request['character_options']['skirt_profile'],SKIRT_PROFILES[2])

    def test_unknown_character_recipe_is_rejected_before_reservation(self):
        for options in ({},dict(skirt_profile='custom'),dict(skirt_profile=None,path='user.py')):
            with self.subTest(options=options),self.assertRaisesRegex(RuntimeError,'production_character_options_invalid'):
                self.manager.submit(dict(self.body,character_options=options))
        self.assertEqual(self.manager.list(),[])
        self.assertEqual(self.calls,{})

    def test_source_failure_does_not_launch_or_claim_review(self):
        self.motion.update(status='failed',reason_code='motion_generation_failed')
        self.psd.update(status='succeeded',project_id='new-project')
        value=self.wait(self.manager.submit(self.body)['job_id'],'blocked')
        self.assertEqual(value['reason_code'],'motion_generation_failed')
        self.assertEqual(self.calls,{})

    def test_changed_source_request_is_not_silently_used(self):
        job=self.manager.submit(self.body)['job_id'];self.wait(job,'running')
        (self.root/'motion/request.json').write_bytes(canonical_bytes(dict(kind='generate',generation=dict(prompt='Walk.'))))
        value=self.wait(job,'blocked')
        self.assertEqual(value['reason_code'],'production_entrance_source_changed')
        self.assertEqual(self.calls,{})

    def test_existing_project_and_wrong_revision(self):
        body=deepcopy(self.body);body['character']=dict(project_id='existing')
        job=self.manager.submit(body)['job_id']
        with self.assertRaisesRegex(RuntimeError,'conflict'):
            self.manager.resume(job,0)
        self.motion.update(status='succeeded',result=dict(motion_status='compiled'))
        value=self.wait(job,'linked')
        self.assertEqual(self.calls[value['run_id']]['project_id'],'existing')

    def test_canceled_source_handoff_cannot_launch_later(self):
        job=self.manager.submit(self.body)['job_id'];value=self.wait(job,'running')
        self.manager.cancel(job,value['revision'])
        self.psd.update(status='succeeded',project_id='new-project')
        self.motion.update(status='succeeded',result=dict(motion_status='compiled'))
        time.sleep(.04)
        self.assertEqual(self.manager.get(job)['status'],'canceled')
        self.assertEqual(self.calls,{})
