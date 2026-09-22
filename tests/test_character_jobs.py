"""Durability, cancellation and exact-source downloads for composed characters."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from autospine_workbench.automation.character_jobs import CharacterJobs
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.storage_io import canonical_bytes


class CharacterJobsTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.projects=SimpleNamespace(state_root=self.root,get_project=lambda _: {})
        self.info={'source_addresses':{'resolved_project_sha256':'a'*64,'input_identity_sha256':'b'*64}}
        self.sleeve_job=dict(status='needs_review',candidate_withdrawn=False,authority='none')
        folder=self.root/'sleeve';folder.mkdir();(folder/'request.json').write_bytes(canonical_bytes({'project_id':'sample'}))
        self.sleeves=Mock();self.sleeves._path.return_value=folder;self.sleeves.get.side_effect=lambda *_:self.sleeve_job
        self.app=SimpleNamespace(store=AnimatedStore(self.root))
        guard=patch('autospine_workbench.automation.character_jobs.inspect_registration',side_effect=lambda *_:self.info)
        guard.start();self.addCleanup(guard.stop)

    def builder(self,*_,progress,cancel_requested):
        progress('compose')
        sources=dict(self.info['source_addresses'],sleeve_job_sha256=canonical_sha256(self.sleeve_job))
        digest=self.app.store.publish({'character-manifest.json':json.dumps({'source_addresses':sources}).encode()})
        return {'artifact_sha256':digest,'manifest':{'layers':[],'animations':['flex']}}

    def manager(self,builder=None):
        manager=CharacterJobs(self.projects,self.sleeves,application=self.app,builder=builder or self.builder,
                              capturer=lambda *_,**kw: {'status':'unavailable'})
        self.addCleanup(manager.close);return manager

    def submit(self,manager):return manager.submit('sample','a'*64,'b'*64,'sleeve-job')

    def terminal(self,manager,job):
        until=monotonic()+5
        while monotonic()<until:
            result=manager.get('sample',job['job_id'])
            if result['status'] not in ('pending','running'):return result
            sleep(.01)
        self.fail('worker did not finish')

    def test_restart_download_and_source_invalidation(self):
        manager=self.manager();job=self.submit(manager)
        self.assertEqual(self.terminal(manager,job)['status'],'needs_review')
        self.assertTrue(manager.download('sample',job['job_id']).startswith(b'PK'))
        manager.close();resumed=self.manager()
        self.assertEqual(resumed.get('sample',job['job_id'])['status'],'needs_review')
        with self.assertRaisesRegex(RuntimeError,'pipeline_job_not_found'):resumed.get('other',job['job_id'])
        self.info['source_addresses']['input_identity_sha256']='c'*64
        self.assertEqual(resumed.get('sample',job['job_id'])['status'],'blocked')
        with self.assertRaises(RuntimeError):resumed.download('sample',job['job_id'])

    def test_motion_target_preserves_fresh_source_checks_without_composition_overview(self):
        manager = self.manager()
        self.assertIsNone(manager.motion_target('sample')['job'])
        job = self.submit(manager)
        self.assertEqual(self.terminal(manager, job)['status'], 'needs_review')
        with patch.object(manager, 'overview', side_effect=AssertionError('unused composition options')):
            target = manager.motion_target('sample')
            self.assertEqual(target['job']['job_id'], job['job_id'])
            self.assertEqual(target['job']['status'], 'needs_review')
            self.assertIsNone(manager.motion_target('other')['job'])
            self.info['source_addresses']['input_identity_sha256'] = 'c'*64
            self.assertEqual(manager.motion_target('sample')['job']['status'], 'blocked')

    def test_component_stage_follows_exclusions_and_precedes_capture(self):
        stages=[]; manager=self.manager()
        def stage(name):
            def apply(*args,**kwargs): stages.append('post' if kwargs.get('stage')=='after_components' else name); return args[-1]
            return apply
        def capture(*args,**kwargs): stages.append('capture'); return {'status':'unavailable'}
        manager.capturer=capture
        with patch('autospine_workbench.automation.character_final_regions.apply_saved',side_effect=stage('final')), \
                patch('autospine_workbench.automation.character_component_mounts.apply_saved',side_effect=stage('mount')), \
                patch('autospine_workbench.automation.character_order_review.apply_saved',side_effect=stage('order')):
            result=self.terminal(manager,self.submit(manager))
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(stages,['final','mount','post','order','capture'])

    def test_shoulder_recipe_is_durable_and_runs_before_final_decisions(self):
        stages=[];manager=self.manager()
        def repair(_manager,request,result,**kwargs):
            self.assertEqual(request['shoulder_regions'],['layer-003','layer-004'])
            stages.append('shoulder')
            return dict(result,shoulder_trial={'status':'blocked','included_in_candidate':False})
        def final(_manager,request,result,**kwargs):
            stages.append('post' if kwargs else 'final');return result
        with patch('autospine_workbench.automation.character_shoulder_trial.apply_selected',side_effect=repair), \
                patch('autospine_workbench.automation.character_final_regions.apply_saved',side_effect=final):
            job=manager.submit('sample','a'*64,'b'*64,'sleeve-job',shoulder_regions=['layer-004','layer-003'])
            result=self.terminal(manager,job)
        self.assertEqual(stages,['shoulder','final','post'])
        self.assertEqual(result['status'],'needs_review')
        self.assertFalse(result['shoulder_trial']['included_in_candidate'])
        request=json.loads((manager._path(job['job_id'])/'request.json').read_text())
        self.assertEqual(request['shoulder_regions'],['layer-003','layer-004'])
        self.assertTrue(manager.download('sample',job['job_id']).startswith(b'PK'))

    def test_cancel_and_duplicate_request_do_not_publish_download(self):
        started=Event();release=Event();self.addCleanup(release.set)
        def build(*args,**kwargs):
            started.set();release.wait(3);return self.builder(*args,**kwargs)
        manager=self.manager(build);job=self.submit(manager);self.assertTrue(started.wait(1))
        self.assertEqual(self.submit(manager)['job_id'],job['job_id'])
        manager.cancel('sample',job['job_id']);release.set()
        self.assertEqual(self.terminal(manager,job)['status'],'canceled')
        with self.assertRaises(RuntimeError):manager.download('sample',job['job_id'])

    def test_withdrawn_sleeve_rejects_build_and_completed_download(self):
        manager=self.manager();job=self.submit(manager);self.terminal(manager,job)
        self.sleeve_job['candidate_withdrawn']=True
        with self.assertRaisesRegex(RuntimeError,'sleeve_unavailable'):self.submit(manager)
        self.assertEqual(manager.get('sample',job['job_id'])['status'],'blocked')

    def test_interrupted_request_and_cross_artifact_reference(self):
        manager=self.manager();job=self.submit(manager);result=self.terminal(manager,job)
        path=manager._path(job['job_id'])/'result.json'
        wrong=manager.application.store.publish({'character-manifest.json':json.dumps({'source_addresses':{
            'resolved_project_sha256':'c'*64,'input_identity_sha256':'b'*64,'sleeve_job_sha256':'d'*64}}).encode()})
        result['artifact_sha256']=wrong;path.write_bytes(canonical_bytes(result))
        with self.assertRaisesRegex(RuntimeError,'artifact_source'):manager.download('sample',job['job_id'])
        path.unlink();self.assertEqual(manager.get('sample',job['job_id'])['reason_code'],'character_build_interrupted')

    def test_runtime_review_is_inventory_bound_and_invalidated(self):
        from hashlib import sha256
        manager=self.manager()
        def capture(*args,**kwargs):
            root=args[3]/'runtime';root.mkdir();raw=b'<p>bounded candidate</p>'
            (root/'index.html').write_bytes(raw)
            return {'status':'needs_review','files':{'index.html':sha256(raw).hexdigest()}}
        manager.capturer=capture;job=self.submit(manager);self.terminal(manager,job)
        self.assertEqual(manager.review_file('sample',job['job_id'],['index.html'])[0],b'<p>bounded candidate</p>')
        with self.assertRaises(RuntimeError):manager.review_file('sample',job['job_id'],['capture-0.log'])
        (manager._path(job['job_id'])/'runtime/index.html').write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError,'artifact_invalid'):manager.review_file('sample',job['job_id'],['index.html'])
        self.info['source_addresses']['input_identity_sha256']='c'*64
        with self.assertRaisesRegex(RuntimeError,'preview_not_ready'):manager.review_file('sample',job['job_id'],['index.html'])

    def test_ordinary_request_binds_route_revision_and_invalidates_after_change(self):
        with patch('autospine_workbench.automation.character_jobs.route_source',return_value='d'*64) as route:
            def build(*_,**kwargs):
                sources=dict(self.info['source_addresses'],route_choice_sha256='d'*64)
                digest=self.app.store.publish({'character-manifest.json':json.dumps({'source_addresses':sources}).encode()})
                return {'artifact_sha256':digest,'manifest':{'layers':[],'animations':['limb-flex-15']}}
            manager=self.manager(build);job=manager.submit('sample','a'*64,'b'*64,None)
            self.assertEqual(self.terminal(manager,job)['status'],'needs_review')
            self.assertTrue(manager.download('sample',job['job_id']).startswith(b'PK'))
            route.return_value='e'*64
            self.assertEqual(manager.get('sample',job['job_id'])['status'],'blocked')
            with self.assertRaises(RuntimeError):manager.download('sample',job['job_id'])
