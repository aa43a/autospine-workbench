from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from autospine_workbench.automation.character_review_context import load
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.automation.pipeline_run import PipelineRunError


class ReviewContextTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'runtime').mkdir();report=raw({'passed':True})
        (self.root/'runtime/report.json').write_bytes(report)
        request=dict(expected_resolved_sha256='a'*64,expected_input_sha256='b'*64,
                     sleeve_job_id=None,route_choice_sha256='c'*64)
        (self.root/'request.json').write_bytes(raw(request))
        self.files={'character-manifest.json':raw(dict(source_addresses=dict(resolved_project_sha256='a'*64,
            input_identity_sha256='b'*64,route_choice_sha256='c'*64)))}
        result=dict(status='needs_review',artifact_sha256='d'*64,
                    runtime=dict(files={'report.json':sha256(report).hexdigest()}))
        self.manager=SimpleNamespace(get=Mock(return_value=result),_current=Mock(),_path=lambda _:self.root,
            application=SimpleNamespace(store=SimpleNamespace(read=Mock(return_value=self.files))))

    def test_one_verified_read_and_fresh_checks_on_each_request(self):
        result,files,report=load(self.manager,'p','job')
        self.assertTrue(json.loads(report)['passed']);self.assertIs(files,self.files)
        self.manager.get.assert_called_once_with('p','job')
        self.manager.application.store.read.assert_called_once_with('d'*64)
        self.manager._current.assert_called_once()
        (self.root/'runtime/report.json').write_bytes(raw({'passed':False}))
        with self.assertRaisesRegex(RuntimeError,'artifact_invalid'):load(self.manager,'p','job')

    def test_source_changed_during_read_is_rejected(self):
        self.manager._current.side_effect=PipelineRunError('project_snapshot_stale')
        with self.assertRaisesRegex(RuntimeError,'snapshot_stale'):load(self.manager,'p','job')

    def test_candidate_cannot_claim_another_input(self):
        manifest=json.loads(self.files['character-manifest.json'])
        manifest['source_addresses']['input_identity_sha256']='e'*64
        self.files['character-manifest.json']=raw(manifest)
        with self.assertRaisesRegex(RuntimeError,'source_mismatch'):load(self.manager,'p','job')
