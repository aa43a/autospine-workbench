from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from zipfile import ZipFile
import test_motion_related_evidence as fixtures
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_related_candidates import register,load,read,entries
from autospine_workbench.automation.motion_related_evidence import bundle_digest


class RelatedCandidateTests(unittest.TestCase):
    def test_append_only_playback_and_download_same_asset(self):
        f=fixtures.RelatedEvidenceTests();f.setUp()
        with TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'job';folder.mkdir()
            AnimatedStore(root).publish(f.base)
            (folder/'request.json').write_bytes(canonical_bytes(f.request))
            manager=SimpleNamespace(state_root=root,_lock=RLock(),folder=lambda _:folder,
                get=lambda _:dict(kind='adapt',status='succeeded',result=dict(artifact_sha256='baseline')),
                projects=None)
            digest=register(manager,'job',f.files,f.receipt,f.runtime,f.visual)
            self.assertEqual(register(manager,'job',f.files,f.receipt,f.runtime,f.visual),digest)
            self.assertEqual(entries(folder),[digest])
            raw,_=read(manager,'job',['related-candidates.json']);rows=json.loads(raw)['rows']
            self.assertEqual(rows[0]['candidate_sha256'],f.receipt['candidate_bundle_sha256'])
            raw,mime=read(manager,'job',['related-candidates',digest,'candidate.zip'])
            self.assertEqual(mime,'application/zip')
            with ZipFile(BytesIO(raw)) as zip:
                self.assertEqual(zip.read('skeleton.json'),f.files['skeleton.json'])
                self.assertEqual(json.loads(zip.read('related-evidence.json'))['visual'],f.visual)
                manifest=json.loads(zip.read('related-export.json'))
                restored={name:zip.read(name) for name in manifest['candidate_files']}
                self.assertEqual(restored,f.files)
                self.assertEqual(bundle_digest(restored),manifest['candidate_sha256'])
                self.assertEqual(json.loads(zip.read('related-receipt.json')),f.receipt)
                self.assertFalse(manifest['selected'])
            page,_=read(manager,'job',['related-candidates',digest,'player.html'])
            self.assertNotIn(b'href="index.html"',page)
            self.assertFalse((folder/'stage-reviews').exists())
            manager.get=lambda _:dict(kind='adapt',status='succeeded',result=dict(artifact_sha256='changed'))
            with self.assertRaisesRegex(ValueError,'baseline_changed'):load(manager,'job',digest)
            with self.assertRaisesRegex(ValueError,'unregistered'):load(manager,'job','../other')
