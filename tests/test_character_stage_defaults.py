from copy import deepcopy
import json
from unittest.mock import patch

from test_character_weighted_review import WeightedReviewTests
from autospine_workbench.automation.character_stage_defaults import evaluate, publish
from autospine_workbench.automation.character_weighted_review import overview, save, confirmed_layers


class StageDefaultTests(WeightedReviewTests):
    def test_default_is_reversible_without_human_acceptance(self):
        self.layer['name']='headwear-front'
        self.result['runtime'].update(frames=1,geometry_failed_records=0)
        skeleton=dict(bones=[dict(name='head')],skins=[dict(attachments={
            'arm-left':{'arm-left':dict(type='mesh',uvs=[0,0],vertices=[1,0,0,0,1])}})])
        files={'skeleton.json':json.dumps(skeleton).encode(),
               'character-manifest.json':json.dumps(dict(layers=self.result['layers'])).encode()}
        self.manager.application.store.read=lambda _:files
        publish(self.manager._path('j'),self.result,files)
        value=overview(self.manager,'p','j')
        self.assertIsNone(value['review'])
        self.assertEqual(value['default_review']['decision_source'],'policy_auto')
        from pathlib import Path
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/character-stage-defaults-v1.schema.json').read_bytes())
        Draft202012Validator(schema).validate(value['default_review'])
        self.assertEqual(confirmed_layers(self.result,value),{'arm'})
        revoked=save(self.manager,'p','j',dict(self.body,action='revoke'))
        self.assertEqual(confirmed_layers(self.result,revoked),set())
        self.assertEqual(confirmed_layers(self.result,overview(self.manager,'p','j')),set())
        self.assertEqual(revoked['review']['accepted_layer_ids'],[])
        changed=deepcopy(self.result);changed['artifact_sha256']='f'*64
        self.assertEqual(confirmed_layers(changed,value),set())

    def test_rebuild_preserves_prior_human_revocation(self):
        from pathlib import Path
        from autospine_workbench.automation.character_stage_defaults import previous_overrides
        first=save(self.manager,'p','j',self.body)
        save(self.manager,'p','j',dict(self.body,action='revoke',expected_review_sha256=first['review_sha256']))
        root=self.manager._path('j')
        old=root/'job-old';old.mkdir()
        (root/'weighted-review').rename(old/'weighted-review')
        self.assertEqual(previous_overrides(root/'job-new','p'),{'arm'})
        self.assertEqual(previous_overrides(root/'job-new','other'),set())
        self.layer['name']='headwear-front'
        self.result['runtime'].update(frames=10,geometry_failed_records=0)
        inventory=dict(regions=[dict(layer_id='arm',region_id='arm-left',influences=[dict(bone='head')])])
        with patch('autospine_workbench.automation.character_stage_defaults.inspect',return_value=inventory):
            self.assertEqual(evaluate(self.result,{'skeleton.json':b'{}'},{'arm'})['accepted_layer_ids'],[])

    def test_unsupported_or_failed_regions_are_not_defaults(self):
        inventory=dict(regions=[dict(layer_id='arm',region_id='arm-left',influences=[dict(bone='head')])])
        self.layer['name']='headwear-front'
        self.result['runtime'].update(frames=10,geometry_failed_records=0)
        with patch('autospine_workbench.automation.character_stage_defaults.inspect',return_value=inventory):
            self.assertEqual(evaluate(self.result,{'skeleton.json':b'{}'})['accepted_layer_ids'],['arm'])
            self.layer['state']='partial'
            self.assertEqual(evaluate(self.result,{'skeleton.json':b'{}'})['accepted_layer_ids'],[])
            self.layer['state']='weighted_candidate'
            inventory['regions'][0]['influences'][0]['bone']='foot_l'
            self.assertEqual(evaluate(self.result,{'skeleton.json':b'{}'})['accepted_layer_ids'],[])
            inventory['regions'][0]['influences'][0]['bone']='head'
            self.result['runtime']['geometry_status']='failed'
            self.assertEqual(evaluate(self.result,{'skeleton.json':b'{}'})['accepted_layer_ids'],[])
