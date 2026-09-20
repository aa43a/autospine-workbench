import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_target_jobs import review_file
from autospine_workbench.automation.pipeline_run import PipelineRunError


class ReadinessIOTests(unittest.TestCase):
    def test_single_artifact_read_preserves_runtime_digest_check(self):
        with TemporaryDirectory() as temporary:
            folder=Path(temporary); (folder/'runtime').mkdir()
            raw=b'{"bundle_sha256":"artifact","passed":true,"results":[{}]}'
            report=folder/'runtime/report.json'; report.write_bytes(raw)
            result=dict(artifact_sha256='artifact',runtime=dict(files={'report.json':sha256(raw).hexdigest()}))
            files={'skeleton.json':b'{}'}
            store=SimpleNamespace(read=lambda digest:files)
            manager=SimpleNamespace(folder=lambda job:folder,
                get=lambda job:dict(kind='adapt',status='succeeded',result=result),
                character_manager=lambda:SimpleNamespace(application=SimpleNamespace(store=store)))
            with patch.object(store,'read',wraps=store.read) as read:
                value=json.loads(review_file(manager,'job',['readiness.json'])[0])
                read.assert_called_once_with('artifact')
            self.assertEqual(value['stages'][-1]['status'],'sampled_pass')
            report.write_bytes(b'{"passed":true}')
            with self.assertRaisesRegex(PipelineRunError,'artifact_invalid'):
                review_file(manager,'job',['readiness.json'])

    def test_missing_runtime_inventory_is_unmeasured_not_passed(self):
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=({'artifact_sha256':'artifact'}, {'skeleton.json':b'{}'})):
            report=json.loads(review_file(None,'job',['readiness.json'])[0])
        self.assertEqual(report['stages'][-1]['status'],'unmeasured')


if __name__=='__main__': unittest.main()
