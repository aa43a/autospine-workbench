import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
from autospine_workbench.automation.sleeve_routes import dispatch_sleeves
from autospine_workbench.automation.storage_io import publish_document


class SleeveWebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.sha='a'*64
        store=SimpleNamespace(workspace_root=self.root,state_root=self.root/'state',
            get_project=lambda project:{'resolved':{'sha256':self.sha}})
        self.manager=SleeveWebJobs(store)
        draft=self.manager.drafts/'huiye/draft.json';draft.parent.mkdir(parents=True);draft.write_text('{}')

    def tearDown(self):
        self.manager.close();self.temp.cleanup()

    def submit(self):
        with patch.object(self.manager._pool,'submit'):
            return self.manager.submit('huiye',self.sha)

    def test_reserved_identity_and_changed_draft_guard(self):
        from autospine_workbench.automation.production_submission import reserved_child
        job = 'job-'+'e'*32
        with patch.object(self.manager._pool,'submit'), reserved_child(job):
            result = self.manager.submit('huiye', self.sha, self.manager._draft_sha('huiye'))
        self.assertEqual(result['job_id'], job)
        with self.assertRaisesRegex(RuntimeError, 'sleeve_draft_changed'):
            self.manager.submit('huiye', self.sha, 'f'*64)

    def test_history_guard_avoids_annotation_readiness_and_retains_canceled_jobs(self):
        self.assertFalse(self.manager.has_job('huiye'))
        job = self.submit()
        with patch('autospine_workbench.automation.sleeve_draft_source.available',
                   side_effect=AssertionError('unnecessary annotation load')):
            self.assertTrue(self.manager.has_job('huiye'))
            self.assertFalse(self.manager.has_job('uuz'))
            self.manager.cancel('huiye', job['job_id'])
            self.manager._jobs.clear()
            self.assertTrue(self.manager.has_job('huiye'))

    def test_history_guard_does_not_ignore_unreadable_requests(self):
        job = self.submit()
        path = self.manager._path(job['job_id']) / 'request.json'
        original = path.read_bytes()
        try:
            path.write_text('invalid')
            with self.assertRaises((ValueError, RuntimeError)):
                self.manager.has_job('huiye')
        finally:
            path.write_bytes(original)

    def test_pending_cancel_is_persistent_idempotent_and_skips_execution(self):
        job=self.submit();job_id=job['job_id'];root=self.manager._path(job_id)
        with self.assertRaisesRegex(RuntimeError,'not_found'):self.manager.cancel('uuz',job_id)
        canceled=self.manager.cancel('huiye',job_id)
        self.assertEqual(canceled['status'],'canceled')
        self.assertEqual(self.manager.cancel('huiye',job_id),canceled)
        with patch('autospine_workbench.automation.sleeve_web_jobs.SleeveProcessTree') as launch:
            self.manager._execute(job_id,json.loads((root/'request.json').read_bytes()))
            launch.assert_not_called()
        self.manager._jobs.clear()
        self.assertEqual(self.manager.get('huiye',job_id)['status'],'canceled')
        self.assertNotEqual(self.submit()['job_id'],job_id)

    def test_running_cancel_targets_only_owned_tree(self):
        job_id=self.submit()['job_id'];other_id=self.submit()['job_id']
        # Same-project active submissions are intentionally deduplicated.
        self.assertEqual(job_id,other_id)
        owned=MagicMock();unrelated=MagicMock()
        self.manager._processes={job_id:owned,'unrelated':unrelated}
        self.manager._jobs[job_id]['status']='running'
        self.sha='b'*64  # Stale source does not prevent stopping own computation.
        response=self.manager.cancel('huiye',job_id)
        self.assertTrue(response['cancel_requested']);self.assertEqual(response['status'],'running')
        owned.terminate.assert_called_once();unrelated.terminate.assert_not_called()
        self.manager._jobs[job_id]['status']='canceled'

    def test_running_worker_persists_cancel_instead_of_process_failure(self):
        job_id=self.submit()['job_id'];root=self.manager._path(job_id)
        request=json.loads((root/'request.json').read_bytes())
        tree=MagicMock();tree.__enter__.return_value=tree;tree.process.wait.return_value=125
        def output():
            yield 'ordinary-deform: running\n'
            self.manager.cancel('huiye',job_id)
            self.assertEqual(self.manager._jobs[job_id]['status'],'running')
        tree.process.stdout=output()
        with patch('autospine_workbench.automation.sleeve_web_jobs.SleeveProcessTree',return_value=tree):
            self.manager._execute(job_id,request)
        value=self.manager.get('huiye',job_id)
        self.assertEqual(value['status'],'canceled');self.assertNotIn('result',value)
        self.assertEqual(value['reason_code'],'sleeve_job_canceled')
        self.assertNotIn(job_id,self.manager._processes)
        tree.release.assert_called_once();tree.terminate.assert_called_once()

    def test_cancel_api_requires_intent_and_empty_body(self):
        from email.message import Message
        replies=[];headers=Message();headers['Host']='localhost:8918'
        handler=SimpleNamespace(headers=headers,_send_visual_json=lambda status,payload:replies.append((status,payload)))
        tail=['jobs','job-'+'a'*32,'cancel']
        dispatch_sleeves(tail,handler,'POST','huiye');self.assertEqual(replies[-1][0],403)
        headers['Origin']='http://localhost:8918';headers['X-Autospine-Intent']='pipeline-preview'
        with patch('autospine_workbench.automation.sleeve_routes.read_json_object_request',return_value={'pid':123}):
            dispatch_sleeves(tail,handler,'POST','huiye')
        self.assertEqual(replies[-1][1]['reason_code'],'pipeline_request_invalid')

    def test_queue_deduplicates_and_restart_is_interrupted(self):
        first=self.submit();self.assertEqual(first,self.submit())
        self.assertEqual(self.manager.overview('huiye')['job'],first)
        with self.assertRaisesRegex(RuntimeError,'not_found'):self.manager.get('uuz',first['job_id'])
        self.manager._jobs.clear()
        self.assertEqual(self.manager.get('huiye',first['job_id'])['reason_code'],'sleeve_job_interrupted')
        with self.assertRaisesRegex(RuntimeError,'snapshot_stale'):self.manager.submit('huiye','b'*64)
        with self.assertRaisesRegex(RuntimeError,'draft_missing'):self.manager.submit('uuz',self.sha)

    def test_download_pins_project_draft_and_zip_bytes(self):
        job=self.submit();job_id=job['job_id'];run=self.manager.output/'huiye/run-example'
        path=run/'spine/huiye/right/candidate.zip';path.parent.mkdir(parents=True);path.write_bytes(b'zip')
        receipts=run/'receipts';receipts.mkdir()
        publish_document(receipts/'spine.json',{'files':{'huiye/right/candidate.zip':hashlib.sha256(b'zip').hexdigest()}},staging=run/'.staging')
        root=self.manager._path(job_id)
        publish_document(root/'result-location.json',{'directory':str(run)},staging=root/'.staging')
        self.manager._jobs[job_id].update(status='needs_review',result={'records':[{'status':'candidate_exported','download':'spine/huiye/right/candidate.zip'}]})
        self.assertEqual(self.manager.download('huiye',job_id,0),b'zip')
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError,'cached_output_changed'):self.manager.download('huiye',job_id,0)
        path.write_bytes(b'zip');self.sha='b'*64
        with self.assertRaisesRegex(RuntimeError,'snapshot_stale'):self.manager.download('huiye',job_id,0)
        self.sha='a'*64;(self.manager.drafts/'huiye/draft.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(RuntimeError,'draft_changed'):self.manager.download('huiye',job_id,0)
        stale = self.manager.overview('huiye')['job']
        self.assertEqual(stale['job_id'], job_id)
        self.assertEqual(stale['reason_code'], 'sleeve_draft_changed')
        self.assertNotIn('result', stale)

    def test_stale_task_stays_visible_after_restart_without_exposing_old_outputs(self):
        job_id, path = self.candidate()
        original = (self.manager._path(job_id)/'result.json').read_bytes()
        self.manager._jobs.clear(); self.sha='b'*64
        overview = self.manager.overview('huiye')
        self.assertTrue(overview['can_build'])
        self.assertEqual(overview['job']['status'], 'blocked')
        self.assertEqual(overview['job']['reason_code'], 'project_snapshot_stale')
        self.assertNotIn('result', overview['job'])
        self.assertNotIn('step', overview['job'])
        self.assertEqual((self.manager._path(job_id)/'result.json').read_bytes(), original)
        with self.assertRaisesRegex(RuntimeError, 'snapshot_stale'):
            self.manager.download('huiye', job_id, 0)
        self.sha='a'*64
        self.assertEqual(self.manager.overview('huiye')['job']['status'], 'needs_review')

    def test_routes_require_mutation_headers_and_never_accept_paths(self):
        from email.message import Message
        replies=[];headers=Message();headers['Host']='localhost:8918'
        handler=SimpleNamespace(headers=headers,_send_visual_json=lambda status,payload:replies.append((status,payload)))
        self.assertTrue(dispatch_sleeves([],handler,'POST','huiye'))
        self.assertEqual(replies[-1][0],403)
        headers['Origin']='http://localhost:8918';headers['X-Autospine-Intent']='pipeline-preview'
        with patch('autospine_workbench.automation.sleeve_routes.read_json_object_request',return_value={'path':'arbitrary'}):
            dispatch_sleeves([],handler,'POST','huiye')
        self.assertEqual(replies[-1][1]['reason_code'],'pipeline_request_invalid')

    def test_all_regions_blocked_is_a_quality_result_not_execution_failure(self):
        job=self.submit();job_id=job['job_id'];root=self.manager._path(job_id)
        run=self.manager.output/'huiye/run-blocked';run.mkdir(parents=True)
        report=dict(schema='autospine.sleeve-workflow/v1',project_id='huiye',status='blocked',
            authority='none',production_authorized=False,steps=[dict(cached=False)],
            records=[dict(status='blocked',download=None,reason_code='official_framebuffer_contact_failure')])
        publish_document(run/'report.json',report,staging=run/'.staging')
        process=MagicMock();process.__enter__.return_value=process;process.wait.return_value=0
        def progress():
            for stage in ('weights','ordinary-repair','ordinary-deform','ordinary-interpolation'):
                for status in ('running','succeeded','cached'):
                    line=f'{stage}: {status}'
                    yield line+'\n'
                    self.assertEqual(self.manager._jobs[job_id]['step'],line)
            yield '../ordinary-deform: running\n'
            self.assertEqual(self.manager._jobs[job_id]['step'],'ordinary-interpolation: cached')
            yield json.dumps(dict(project_id='huiye',review=str(run/'index.html')))+'\n'
        process.stdout=progress()
        request=json.loads((root/'request.json').read_bytes())
        tree=MagicMock();tree.__enter__.return_value=tree;tree.process=process
        with patch('autospine_workbench.automation.sleeve_web_jobs.SleeveProcessTree',return_value=tree):
            self.manager._execute(job_id,request)
        result=self.manager.get('huiye',job_id)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['result'],report)
        with self.assertRaisesRegex(RuntimeError,'preview_not_ready'):
            self.manager.download('huiye',job_id,0)

    def candidate(self):
        job_id=self.submit()['job_id'];root=self.manager._path(job_id)
        run=self.manager.output/'huiye'/job_id
        path=run/'spine/huiye/right/candidate.zip';path.parent.mkdir(parents=True);path.write_bytes(b'zip')
        (run/'receipts').mkdir()
        publish_document(run/'receipts/spine.json',{'files':{'huiye/right/candidate.zip':hashlib.sha256(b'zip').hexdigest()}},staging=run/'.staging')
        publish_document(root/'result-location.json',{'directory':str(run)},staging=root/'.staging')
        self.manager._jobs[job_id].update(status='needs_review',result={'records':[
            {'status':'candidate_exported','download':'spine/huiye/right/candidate.zip'},
            {'status':'blocked','download':None}]})
        publish_document(root/'result.json',self.manager._jobs[job_id],staging=root/'.staging')
        return job_id,path

    def visibility(self,job_id,revision,withdrawn,project='huiye'):
        return self.manager.set_visibility(project,job_id,'a'*64,revision,withdrawn=withdrawn)

    def test_visibility_withdraw_restore_idempotent_persistent_and_job_scoped(self):
        job_id,path=self.candidate();source=path.read_bytes()
        withdrawn=self.visibility(job_id,0,True)
        self.assertTrue(withdrawn['candidate_withdrawn']);self.assertNotIn('result',withdrawn)
        self.assertEqual(self.visibility(job_id,0,True),withdrawn)
        self.manager._jobs.clear()
        self.assertEqual(self.manager.get('huiye',job_id),withdrawn)
        self.assertTrue(self.manager.overview('huiye')['job']['candidate_withdrawn'])
        with self.assertRaisesRegex(RuntimeError,'candidate_withdrawn'):self.manager.download('huiye',job_id,0)
        restored=self.visibility(job_id,1,False)
        self.assertFalse(restored['candidate_withdrawn']);self.assertEqual(restored['visibility_revision'],2)
        self.assertEqual(self.visibility(job_id,1,False),restored)
        self.assertEqual(self.manager.download('huiye',job_id,0),source)
        with self.assertRaisesRegex(RuntimeError,'preview_not_ready'):self.manager.download('huiye',job_id,1)
        self.visibility(job_id,2,True)
        with self.assertRaisesRegex(RuntimeError,'visibility_conflict'):self.visibility(job_id,1,False)
        new=self.submit();self.assertNotEqual(new['job_id'],job_id);self.assertFalse(new['candidate_withdrawn'])

    def test_restore_rechecks_source_draft_zip_and_preserves_withdrawal_on_failure(self):
        job_id,path=self.candidate();self.visibility(job_id,0,True)
        self.sha='b'*64
        with self.assertRaisesRegex(RuntimeError,'snapshot_stale'):self.visibility(job_id,1,False)
        self.sha='a'*64;draft=self.manager.drafts/'huiye/draft.json';draft.write_text('{"changed":true}')
        with self.assertRaisesRegex(RuntimeError,'draft_changed'):self.visibility(job_id,1,False)
        draft.write_text('{}');path.write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'cached_output_changed'):self.visibility(job_id,1,False)
        self.assertTrue(self.manager.get('huiye',job_id)['candidate_withdrawn'])
        self.assertEqual(self.manager.get('huiye',job_id)['visibility_revision'],1)
        with self.assertRaisesRegex(RuntimeError,'not_found'):self.visibility(job_id,1,False,project='uuz')
        with self.assertRaisesRegex(RuntimeError,'request_invalid'):self.visibility(job_id,True,False)
        path.write_bytes(b'zip');self.manager._jobs[job_id]['status']='blocked'
        with self.assertRaisesRegex(RuntimeError,'preview_not_ready'):self.visibility(job_id,1,False)

    def test_visibility_routes_require_intent_and_fixed_body(self):
        from email.message import Message
        replies=[];headers=Message();headers['Host']='localhost:8918'
        handler=SimpleNamespace(headers=headers,server=object(),_send_visual_json=lambda status,payload:replies.append((status,payload)))
        tail=['jobs','job-'+'a'*32,'withdraw']
        dispatch_sleeves(tail,handler,'POST','huiye');self.assertEqual(replies[-1][0],403)
        headers['Origin']='http://localhost:8918';headers['X-Autospine-Intent']='pipeline-preview'
        with patch('autospine_workbench.automation.sleeve_routes.read_json_object_request',return_value={'path':'arbitrary'}):
            dispatch_sleeves(tail,handler,'POST','huiye')
        self.assertEqual(replies[-1][1]['reason_code'],'pipeline_request_invalid')
        body=dict(expected_resolved_sha256='a'*64,expected_visibility_revision=0)
        manager=MagicMock()
        with patch('autospine_workbench.automation.sleeve_routes.read_json_object_request',return_value=body), patch(
                'autospine_workbench.automation.sleeve_routes.manager_for',return_value=manager):
            dispatch_sleeves(tail,handler,'POST','huiye')
        manager.set_visibility.assert_called_once_with('huiye',tail[1],**body,withdrawn=True)
        self.assertEqual(replies[-1][0],200)

    def test_concurrent_withdrawal_is_one_revision_and_corrupt_journal_fails_closed(self):
        from concurrent.futures import ThreadPoolExecutor
        job_id,path=self.candidate()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.visibility(job_id,0,True),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0]['visibility_revision'],1)
        journal=self.manager._path(job_id)/'visibility/00000001.json'
        journal.write_text('{"revision":1,"withdrawn":"false"}')
        with self.assertRaisesRegex(RuntimeError,'visibility_invalid'):self.manager.download('huiye',job_id,0)
        self.assertEqual(path.read_bytes(),b'zip')
