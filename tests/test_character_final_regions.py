from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from threading import RLock
from hashlib import sha256
import importlib.util
import json
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.character_final_regions import save, overview, apply_saved
from autospine_workbench.automation.storage_io import canonical_bytes


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
class CharacterFinalRegionsTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.files=fixture();manifest=json.loads(self.files['character-manifest.json'])
        for layer in manifest['layers']:
            layer.update(reason_codes=[],missing_region_ids=[])
            for region in layer['regions']:region['state']=layer['state']
        self.files['character-manifest.json']=json.dumps(manifest).encode()
        self.digest=canonical_sha256({n:sha256(b).hexdigest() for n,b in self.files.items()})
        self.result=dict(status='needs_review',artifact_sha256=self.digest)
        self.manager=SimpleNamespace(root=Path(temp.name),_lock=RLock(),projects=SimpleNamespace(get_project=lambda _:None),
            _path=lambda _:Path(temp.name),
            get=lambda *_:self.result,verified_files=lambda *_:self.files,
            application=SimpleNamespace(store=SimpleNamespace(read=lambda _:self.files,publish=lambda _: 'b'*64)))
        self.body=dict(action='replace',expected_head_sha256=None,job_id='job',expected_artifact_sha256=self.digest,
                       regions=[dict(layer_id='skirt',region_id='skirt')])
        (Path(temp.name)/'request.json').write_text('{}')

    def test_save_exact_apply_revoke_and_recovery(self):
        state=save(self.manager,'project',self.body)
        self.assertTrue(state['active']);self.assertEqual(overview(self.manager,'project'),state)
        result=apply_saved(self.manager,dict(project_id='project',final_region_decisions_sha256=state['head_sha256']),self.result)
        self.assertEqual(result['final_region_exclusions']['excluded_region_ids'],['skirt'])
        self.assertEqual(result['manifest']['layers'][0]['state'],'excluded')
        revoked=save(self.manager,'project',dict(action='revoke',expected_head_sha256=state['head_sha256']))
        self.assertFalse(revoked['active'])
        self.assertIs(apply_saved(self.manager,dict(project_id='project',final_region_decisions_sha256=revoked['head_sha256']),self.result),self.result)

    def test_changed_source_or_head_never_reuses_confirmation(self):
        state=save(self.manager,'project',self.body)
        with self.assertRaisesRegex(RuntimeError,'conflict'):save(self.manager,'project',self.body)
        with self.assertRaisesRegex(RuntimeError,'decisions_changed'):
            apply_saved(self.manager,{'project_id':'project'},self.result)
        with self.assertRaisesRegex(RuntimeError,'source_changed'):
            apply_saved(self.manager,dict(project_id='project',final_region_decisions_sha256=state['head_sha256']),{'artifact_sha256':'c'*64})

    def test_invalid_scope_does_not_write_history(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            save(self.manager,'project',{**self.body,'regions':self.body['regions']*2})
        self.assertIsNone(overview(self.manager,'project')['head_sha256'])

    def test_malformed_or_cross_source_history_is_rejected(self):
        save(self.manager,'project',self.body)
        path=self.manager.root/'final-region-decisions/project/000000.json'
        original=json.loads(path.read_bytes())
        for field,value in [('decisions',None),('build_options',{'unexpected':'x'}),('source_bundle_sha256','f'*64)]:
            with self.subTest(field=field):
                path.write_bytes(canonical_bytes({**original,field:value}))
                with self.assertRaisesRegex(RuntimeError,'history_invalid'):overview(self.manager,'project')
