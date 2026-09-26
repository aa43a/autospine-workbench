"""Static player delivery stays cheap; candidate data still fails closed."""
from base64 import b64encode
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_motion_related_evidence as fixtures
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_candidates import read,register
from autospine_workbench.automation.motion_related_evidence import bundle_digest
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes


class RelatedPlayerLoadingTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.folder=self.root/'job';self.folder.mkdir()
        f=fixtures.RelatedEvidenceTests();f.setUp();self.f=f
        f.files.update({'skeleton.atlas':b'texture.png\n','texture.png':b'fixture image'})
        self.candidate=bundle_digest(f.files)
        f.receipt['candidate_bundle_sha256']=self.candidate
        f.runtime.update(bundle_sha256=self.candidate,info={'animations':['external-motion']})
        f.visual['artifact_sha256']=self.candidate
        AnimatedStore(self.root).publish(f.base)
        (self.folder/'request.json').write_bytes(canonical_bytes(f.request))
        self.manager=SimpleNamespace(state_root=self.root,_lock=RLock(),folder=lambda _:self.folder,
            get=lambda _:dict(kind='adapt',status='succeeded',result=dict(artifact_sha256='baseline')),
            projects=None)
        self.digest=register(self.manager,'job',f.files,f.receipt,f.runtime,f.visual)

    def read(self,*tail,digest=None):
        return read(self.manager,'job',['related-candidates',digest or self.digest,*tail])

    def test_shell_and_scripts_do_not_load_candidate_or_diagnostics(self):
        with patch.object(AnimatedStore,'read',side_effect=AssertionError('whole bundle read')):
            for tail in [('player.html',),('player-assets','client.js'),
                         ('player-assets','style.css'),('player-assets','inspection.js')]:
                with self.subTest(tail=tail):
                    raw,mime=self.read(*tail)
                    self.assertTrue(raw);self.assertTrue(mime.startswith('text/'))
            page,_=self.read('player.html')
            self.assertIn(b'href="report.json"',page)
            self.assertNotIn(b'href="setup/index.html"',page)

    def test_shell_still_requires_current_registered_source(self):
        with self.assertRaisesRegex(ValueError,'unregistered'):
            self.read('player.html',digest='e'*64)
        self.manager.get=lambda _:dict(kind='adapt',status='succeeded',result=dict(artifact_sha256='new'))
        with self.assertRaisesRegex(ValueError,'baseline_changed'):self.read('player.html')
        self.manager.get=lambda _:dict(kind='adapt',status='succeeded',result=dict(artifact_sha256='baseline'))
        request={**self.f.request,'new_setting':True}
        (self.folder/'request.json').write_bytes(canonical_bytes(request))
        with self.assertRaisesRegex(ValueError,'baseline_changed'):self.read('player-assets','client.js')

    def test_shell_rejects_corrupt_registration(self):
        store=AnimatedStore(self.root)
        (store.root/self.digest/'related.json').write_bytes(b'{}')
        with self.assertRaisesRegex(PipelineRunError,'artifact_invalid'):self.read('player.html')

    def test_scene_has_same_exact_content(self):
        raw,mime=self.read('player-assets','scene.json');scene=json.loads(raw)
        self.assertEqual(mime,'application/json')
        self.assertEqual(scene['artifact_sha256'],self.candidate)
        self.assertEqual(scene['skeleton'],json.loads(self.f.files['skeleton.json']))
        self.assertEqual(scene['atlas'],self.f.files['skeleton.atlas'].decode())
        self.assertEqual(scene['textures']['texture.png'],
                         'data:image/png;base64,'+b64encode(self.f.files['texture.png']).decode())

    def test_corrupt_texture_cannot_reach_scene_context_runtime_or_export(self):
        store=AnimatedStore(self.root)
        (store.root/self.candidate/'texture.png').write_bytes(b'changed image')
        # A shell can display a load error; serving it does not approve its data.
        self.assertTrue(self.read('player.html')[0])
        for tail in [('player-assets',name) for name in
                     ('scene.json','context.json','runtime.js','texture.png')]+[
                         ('report.json',),('candidate.zip',)]:
            with self.subTest(tail=tail):
                with self.assertRaisesRegex(PipelineRunError,'artifact_invalid'):self.read(*tail)

    def test_scene_still_revalidates_evidence(self):
        with patch('autospine_workbench.automation.motion_related_candidates.inspect',return_value={}):
            with self.assertRaisesRegex(ValueError,'evidence_changed'):self.read('player-assets','scene.json')


if __name__=='__main__':unittest.main()
