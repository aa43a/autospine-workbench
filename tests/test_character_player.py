import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.character_player import read


class CharacterPlayerTests(unittest.TestCase):
    def fixture(self, digest='a'*64):
        report = dict(bundle_sha256=digest, info=dict(width=400,height=600,left=-20,bottom=0),
                      runtime_sha256=sha256(b'runtime').hexdigest(),
                      runtime_package='@esotericsoftware/spine-webgl',runtime_version='4.3.13')
        files = {'skeleton.json':b'{}','skeleton.atlas':b'page.png','page.png':b'png',
                 'private.json':b'do not serve'}
        manager = SimpleNamespace(projects=SimpleNamespace(workspace_root=Path('.')),
            review_context=lambda p,j: (dict(artifact_sha256='a'*64),files,json.dumps(report).encode()))
        return manager

    def test_player_keeps_evidence_separate(self):
        manager = self.fixture()
        html,mime = read(manager,'project','job',['player.html'])
        self.assertIn(b'player-assets/client.js',html)
        self.assertIn(b'player-assets/inspection.js',html)
        script, mime_js = read(manager,'project','job',['player-assets','inspection.js'])
        self.assertIn(b'audit-focus',script)
        self.assertEqual(mime_js,'text/javascript')
        self.assertIn(b'href="index.html"',html)
        self.assertTrue(mime.startswith('text/html'))
        context,_ = read(manager,'project','job',['player-assets','context.json'])
        self.assertEqual(json.loads(context)['artifact_sha256'],'a'*64)
        self.assertEqual(read(manager,'project','job',['player-assets','page.png']),(b'png','image/png'))
        scene,_ = read(manager,'project','job',['player-assets','scene.json'])
        self.assertEqual(json.loads(scene)['textures']['page.png'],'data:image/png;base64,cG5n')

    def test_rejects_changed_source_and_arbitrary_assets(self):
        with self.assertRaisesRegex(RuntimeError,'character_review_source_mismatch'):
            read(self.fixture('b'*64),'p','j',['player-assets','scene.json'])
        for parts in [['player-assets','..','page.png'],['player-assets','private.json'],['player-assets','missing.png']]:
            with self.assertRaisesRegex(RuntimeError,'pipeline_artifact_not_found'):
                read(self.fixture(),'p','j',parts)

    def test_scene_only_transfers_atlas_pages(self):
        manager = self.fixture()
        result, files, report = manager.review_context('p','j')
        files.update({'images/page.png': b'source copy', 'editor/page.png': b'editor copy',
                      'second.png': b'second'})
        files['skeleton.atlas'] = b'page.png\nsize: 1,1\nregion\n bounds: 0,0,1,1\n\nsecond.png\nsize: 1,1\n'
        manager.review_context = lambda *_: (result, files, report)
        scene, _ = read(manager,'p','j',['player-assets','scene.json'])
        self.assertEqual(set(json.loads(scene)['textures']), {'page.png','second.png'})
        self.assertIn('editor/page.png', files)
        del files['second.png']
        with self.assertRaisesRegex(RuntimeError, 'character_player_texture_missing'):
            read(manager,'p','j',['player-assets','scene.json'])

    def test_runtime_must_match_captured_bytes(self):
        with TemporaryDirectory() as folder:
            package=Path(folder)/'node_modules/@esotericsoftware/spine-webgl'
            (package/'dist/iife').mkdir(parents=True)
            (package/'package.json').write_text(json.dumps(dict(name='@esotericsoftware/spine-webgl',version='4.3.13')))
            script=package/'dist/iife/spine-webgl.js';script.write_bytes(b'runtime')
            with patch('autospine_workbench.automation.character_player.discover',return_value=['x',folder]):
                self.assertEqual(read(self.fixture(),'p','j',['player-assets','runtime.js'])[0],b'runtime')
                script.write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError,'character_player_runtime_mismatch'):
                    read(self.fixture(),'p','j',['player-assets','runtime.js'])

    def test_motion_runtime_checks_capture_without_full_bundle_read(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        manager = self.fixture()
        result, _, report = manager.review_context('p','j')
        manager.get = lambda job: dict(kind='adapt',status='succeeded',result=result)
        with TemporaryDirectory() as folder:
            package=Path(folder)/'node_modules/@esotericsoftware/spine-webgl'
            (package/'dist/iife').mkdir(parents=True)
            (package/'package.json').write_text(json.dumps(dict(name='@esotericsoftware/spine-webgl',version='4.3.13')))
            script=package/'dist/iife/spine-webgl.js';script.write_bytes(b'runtime')
            with patch('autospine_workbench.automation.motion_target_jobs.context',side_effect=AssertionError('full bundle read')), \
                 patch('autospine_workbench.automation.motion_target_jobs.runtime_reader',return_value=lambda name: report), \
                 patch('autospine_workbench.automation.character_player.discover',return_value=['x',folder]):
                self.assertEqual(review_file(manager,'j',['player-assets','runtime.js'])[0],b'runtime')
                script.write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError,'character_player_runtime_mismatch'):
                    review_file(manager,'j',['player-assets','runtime.js'])
                manager.get=lambda job: dict(kind='adapt',status='outdated')
                with self.assertRaisesRegex(RuntimeError,'motion_preview_unavailable'):
                    review_file(manager,'j',['player-assets','runtime.js'])


if __name__ == '__main__':
    unittest.main()
