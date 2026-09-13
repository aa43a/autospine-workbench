from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest
from autospine_workbench.automation.character_component_mounts import save, overview, apply_saved
from autospine_workbench.automation.storage_io import canonical_bytes


class CharacterComponentMountsTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        (root/'request.json').write_bytes(canonical_bytes({'skirt_profile':'reviewed-torso-waist-v2'}))
        self.result=dict(status='needs_review',artifact_sha256='a'*64)
        self.manager=SimpleNamespace(root=root,_lock=RLock(),projects=SimpleNamespace(get_project=lambda _:None),
            _path=lambda _:root,get=lambda *_:self.result,verified_files=lambda *_:{'source':b'bytes'},
            application=SimpleNamespace(store=SimpleNamespace(read=lambda _: {'source':b'bytes'},publish=lambda _: 'b'*64)))
        self.decision=dict(schema='autospine.component-mount-decision/v1',source_bundle_sha256='a'*64,
            source_region_id='wing',plan_sha256='c'*64,decision_source='human_confirmation',reversible=True,
            parents={'component-0000':'head','component-0001':'chest'})
        self.body=dict(action='replace',expected_head_sha256=None,job_id='job',decision=self.decision,allowed_parents=['head','chest'])
        self.generate=patch('autospine_workbench.targets.character43.component_mount_candidate.generate',
            return_value=({'character-manifest.json':b'{"layers":[]}'},{'parent_review_required':False})).start()
        self.addCleanup(patch.stopall)

    def test_save_rebuild_recover_revoke(self):
        state=save(self.manager,'project',self.body)
        self.assertEqual(state,overview(self.manager,'project'))
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).parents[1]/'schemas/character-component-mounts-v1.schema.json').read_bytes())
        child=json.loads((Path(__file__).parents[1]/'schemas/component-mount-decision-v1.schema.json').read_bytes())
        schema['properties']['decision']['oneOf'][1]=child
        Draft202012Validator(schema).validate(state['review'])
        self.assertEqual(state['review']['build_options'],{'skirt_profile':'reviewed-torso-waist-v2'})
        request=dict(project_id='project',component_mounts_sha256=state['head_sha256'])
        result=apply_saved(self.manager,request,self.result)
        self.assertEqual(result['artifact_sha256'],'b'*64)
        self.assertFalse(result['component_mounts']['parent_review_required'])
        self.generate.assert_called_with({'source':b'bytes'},'wing',['head','chest'],self.decision)
        original=(self.manager.root/'component-mount-decisions/project/000000.json').read_bytes()
        revoked=save(self.manager,'project',dict(action='revoke',expected_head_sha256=state['head_sha256']))
        self.assertFalse(revoked['active'])
        Draft202012Validator(schema).validate(revoked['review'])
        self.assertEqual(original,(self.manager.root/'component-mount-decisions/project/000000.json').read_bytes())
        self.assertIs(apply_saved(self.manager,dict(project_id='project',component_mounts_sha256=revoked['head_sha256']),self.result),self.result)

    def test_source_and_revision_conflicts(self):
        state=save(self.manager,'project',self.body)
        with self.assertRaisesRegex(RuntimeError,'conflict'): save(self.manager,'project',self.body)
        with self.assertRaisesRegex(RuntimeError,'decisions_changed'): apply_saved(self.manager,{'project_id':'project'},self.result)
        with self.assertRaisesRegex(RuntimeError,'source_changed'):
            apply_saved(self.manager,dict(project_id='project',component_mounts_sha256=state['head_sha256']),{'artifact_sha256':'f'*64})

    def test_invalid_or_adapter_rejected_decision_never_persists(self):
        for decision in [None,dict(self.decision,reversible=1),dict(self.decision,parents={'x':'missing'})]:
            with self.assertRaisesRegex(RuntimeError,'invalid'): save(self.manager,'project',dict(self.body,decision=decision))
        self.generate.side_effect=ValueError('component_mount_decision_source')
        with self.assertRaisesRegex(ValueError,'decision_source'): save(self.manager,'project',self.body)
        self.assertIsNone(overview(self.manager,'project')['head_sha256'])

    def test_tampered_history_fails_closed(self):
        state=save(self.manager,'project',self.body)
        path=self.manager.root/'component-mount-decisions/project/000000.json'
        path.write_bytes(canonical_bytes(dict(state['review'],project_id='other')))
        with self.assertRaisesRegex(RuntimeError,'history_invalid'): overview(self.manager,'project')

    def test_absent_history_is_identity(self):
        self.assertIs(apply_saved(self.manager,{'project_id':'project'},self.result),self.result)
        self.generate.assert_not_called()
