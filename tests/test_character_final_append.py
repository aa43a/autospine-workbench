import json
import unittest
from hashlib import sha256
from test_character_final_regions import CharacterFinalRegionsTests as Fixture
from autospine_workbench.automation.character_final_regions import save,overview
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch


def digest(files):
    return canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()})


class FinalAppendTests(unittest.TestCase):
    def setUp(self):
        Fixture.setUp(self)
        manifest=json.loads(self.files['character-manifest.json'])
        manifest['layers'][1]['state']='static_reference'
        manifest['layers'][1]['regions'][0]['state']='static_reference'
        self.files['character-manifest.json']=canonical_bytes(manifest)
        self.original=dict(self.files);self.digest=digest(self.files)
        self.result['artifact_sha256']=self.digest
        self.body['expected_artifact_sha256']=self.digest
        self.manager.application.store.read=lambda _:self.original
        self.first=save(self.manager,'project',self.body)
        self.files=apply_batch(self.original,self.first['review']['decisions'])
        self.result['artifact_sha256']=digest(self.files)
        self.append=dict(action='append',expected_head_sha256=self.first['head_sha256'],
            job_id='job',expected_artifact_sha256=digest(self.files),
            regions=[dict(layer_id='shirt',region_id='shirt')])

    def test_append_preserves_old_decision_and_replays_complete_batch(self):
        current=save(self.manager,'project',self.append)
        self.assertEqual(current['review']['decisions'][0],self.first['review']['decisions'][0])
        self.assertEqual(current['review']['previous_sha256'],self.first['head_sha256'])
        self.assertEqual(current['review']['source_bundle_sha256'],self.digest)
        output=apply_batch(self.original,current['review']['decisions'])
        self.assertFalse(json.loads(output['skeleton.json'])['slots'])
        self.assertEqual(current['review']['revision'],1)

    def test_changed_rendered_source_and_duplicate_do_not_write(self):
        self.files['images/shirt.png']=b'changed'
        with self.assertRaisesRegex(RuntimeError,'append_source_changed'):
            save(self.manager,'project',self.append)
        self.files=apply_batch(self.original,self.first['review']['decisions'])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            save(self.manager,'project',{**self.append,'regions':self.body['regions']})
        self.assertEqual(overview(self.manager,'project'),self.first)

    def test_changed_head_or_recipe_does_not_write(self):
        with self.assertRaisesRegex(RuntimeError,'conflict'):
            save(self.manager,'project',{**self.append,'expected_head_sha256':None})
        (self.manager.root/'request.json').write_bytes(canonical_bytes({'skirt_profile':'reviewed-torso-waist-v2'}))
        with self.assertRaisesRegex(RuntimeError,'append_source_changed'):
            save(self.manager,'project',self.append)
        self.assertEqual(overview(self.manager,'project'),self.first)
