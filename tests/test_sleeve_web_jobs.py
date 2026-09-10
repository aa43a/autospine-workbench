import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
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
        self.manager._jobs[job_id].update(status='needs_review',result={'records':[{'download':'spine/huiye/right/candidate.zip'}]})
        self.assertEqual(self.manager.download('huiye',job_id,0),b'zip')
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(RuntimeError,'cached_output_changed'):self.manager.download('huiye',job_id,0)
        path.write_bytes(b'zip');self.sha='b'*64
        with self.assertRaisesRegex(RuntimeError,'snapshot_stale'):self.manager.download('huiye',job_id,0)
        self.sha='a'*64;(self.manager.drafts/'huiye/draft.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(RuntimeError,'draft_changed'):self.manager.download('huiye',job_id,0)
        self.assertIsNone(self.manager.overview('huiye')['job'])

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
