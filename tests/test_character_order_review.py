import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
import jsonschema

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_order_review import save, overview, apply_saved
from test_character_order_candidate import fixture


class OrderReviewTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory(); self.addCleanup(temp.cleanup); root=Path(temp.name)
        self.store=AnimatedStore(root); self.files=fixture(); self.digest=self.store.publish(self.files)
        self.result=dict(status='needs_review',artifact_sha256=self.digest)
        self.manager=SimpleNamespace(root=root,_lock=RLock(),projects=SimpleNamespace(get_project=lambda _:None),
            get=lambda *_:self.result, verified_files=lambda *_:self.store.read(self.result['artifact_sha256']),
            _path=lambda _:root,application=SimpleNamespace(store=self.store))
        (root/'request.json').write_text('{"skirt_profile":"example"}')
        self.body=dict(action='replace',expected_head_sha256=None,job_id='job',
                       expected_artifact_sha256=self.digest,constraints=[['leg','skirt']])

    def test_save_restart_apply_and_revoke_restore_base(self):
        state=save(self.manager,'project',self.body)
        self.assertEqual(state,overview(self.manager,'project'))
        result=apply_saved(self.manager,dict(project_id='project',order_decisions_sha256=state['head_sha256']),self.result)
        self.assertNotEqual(result['artifact_sha256'],self.digest)
        self.assertEqual(self.store.read(self.digest),self.files)
        self.assertEqual(state['review']['build_options'],{'skirt_profile':'example'})
        revoked=save(self.manager,'project',dict(action='revoke',expected_head_sha256=state['head_sha256']))
        self.assertFalse(revoked['active'])
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/character-order-review-v1.schema.json').read_text())
        for review in (state['review'], revoked['review']): jsonschema.validate(review,schema)
        self.assertIs(apply_saved(self.manager,dict(project_id='project',order_decisions_sha256=revoked['head_sha256']),self.result),self.result)

    def test_source_conflict_cycle_and_corrupt_history_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'cycle'):
            save(self.manager,'project',{**self.body,'constraints':[['leg','skirt'],['skirt','leg']]})
        self.assertIsNone(overview(self.manager,'project')['head_sha256'])
        state=save(self.manager,'project',self.body)
        with self.assertRaisesRegex(RuntimeError,'conflict'): save(self.manager,'project',self.body)
        with self.assertRaisesRegex(RuntimeError,'decisions_changed'):
            apply_saved(self.manager,{'project_id':'project'},self.result)
        with self.assertRaisesRegex(RuntimeError,'source_changed'):
            apply_saved(self.manager,dict(project_id='project',order_decisions_sha256=state['head_sha256']),{'artifact_sha256':'f'*64})
        path=self.manager.root/'order-decisions/project/000000.json'
        doc=json.loads(path.read_bytes()); doc['production_authorized']=True; path.write_bytes(canonical_bytes(doc))
        with self.assertRaisesRegex(RuntimeError,'history_invalid'):overview(self.manager,'project')

    def test_replace_uses_original_preorder_source(self):
        state=save(self.manager,'project',self.body)
        self.result=apply_saved(self.manager,dict(project_id='project',order_decisions_sha256=state['head_sha256']),self.result)
        state=save(self.manager,'project',{**self.body,'expected_head_sha256':state['head_sha256'],
                   'expected_artifact_sha256':self.result['artifact_sha256'],'constraints':[['face','skirt']]})
        self.assertEqual(state['review']['source_bundle_sha256'],self.digest)
