import json
import unittest
from unittest.mock import patch

from test_server import WorkbenchHttpContractTests as Fixture
from test_pose_geometry_candidate import bundle


class PoseHttpTests(unittest.TestCase):
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    request = Fixture.request

    def test_static_editor_assets_do_not_read_candidate(self):
        from autospine_workbench.automation.motion_pose_geometry_editor import read
        with patch('autospine_workbench.automation.motion_target_jobs.context', side_effect=AssertionError('unneeded candidate read')):
            for name in ('index.html', 'editor.js', 'editor.css', 'pose-source.js', 'motion-source-player.js', 'pose-geometry-metrics.js'):
                raw, mime = read(None, 'unused', ['pose-geometry', 'leg', 'move', '0', name])
                self.assertTrue(raw)
                self.assertTrue(mime.startswith('text/'))

    def test_editor_scope_and_submission_intent(self):
        files, plan = bundle()
        job = 'motion-'+'a'*32
        path = '/api/motions/'+job
        intent = {'Origin': f'http://{self.host}:{self.port}', 'X-Autospine-Intent': 'pipeline-preview'}
        with patch('autospine_workbench.automation.motion_target_jobs.context',
                   return_value=({'artifact_sha256': 'a'*64}, files)):
            code, _, raw = self.request('GET', path+'/view/pose-geometry/leg/move/0/editor-config.json')
            self.assertEqual(code, 200)
            config = json.loads(raw)
            self.assertEqual(config['request']['vertices'], [0, 1, 2, 3])
            self.assertEqual(config['request']['poses'], [])
            self.assertEqual(config['execute_url'], path+'/pose-geometry-execute')
            self.assertEqual(config['source_comparison_url'], 'source-comparison.json')
            for asset in ('pose-source.js', 'motion-source-player.js'):
                self.assertEqual(self.request('GET', path+'/view/pose-geometry/leg/move/0/'+asset)[0], 200)
            with patch('autospine_workbench.automation.motion_source_comparison.build',
                       return_value={'artifact_sha256': 'a'*64, 'source_start': 2}) as comparison:
                code, _, raw = self.request('GET', path+'/view/pose-geometry/leg/move/0/source-comparison.json')
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(raw)['source_start'], 2)
                comparison.assert_called_once()
            self.assertEqual(self.request('GET', path+'/view/pose-geometry/leg/move/999/editor-config.json')[0], 400)
        body = dict(artifact_sha256='a'*64, pose_geometry=plan['pose_geometry'])
        with patch('autospine_workbench.automation.motion_pose_geometry_execution.submit', return_value={'job_id':'new'}) as submit:
            self.assertEqual(self.request('POST', path+'/pose-geometry-execute', body)[0], 403)
            self.assertEqual(self.request('POST', path+'/pose-geometry-execute', body, intent)[0], 202)
            submit.assert_called_once()
            self.assertEqual(submit.call_args.args[1:], (job, body))
        self.assertEqual(self.request('GET', path+'/pose-geometry-execute')[0], 405)
