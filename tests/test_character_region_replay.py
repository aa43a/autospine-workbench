from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
import unittest
from test_character_region_exclusion import fixture
from autospine_workbench.automation.character_region_replay import apply_current, FIXED
from autospine_workbench.automation.storage_io import canonical_bytes as raw


class RegionReplayTests(unittest.TestCase):
    def setUp(self):
        self.original,self.decision=fixture()
        doc=json.loads(self.original['skeleton.json']);doc['bones']=[dict(name='root')]
        self.original['skeleton.json']=raw(doc)
        ref=json.loads(self.original['numeric-reference.json'])
        ref['skeleton_sha256']=sha256(self.original['skeleton.json']).hexdigest()
        self.original['numeric-reference.json']=raw(ref)
        manifest=json.loads(self.original['character-manifest.json'])
        manifest['source_addresses']={k:'a'*64 for k in FIXED|{'animated_registration_sha256','input_identity_sha256','layer_binding_draft_sha256'}}
        self.original['character-manifest.json']=raw(manifest)
        self.decision.update(source_bundle_sha256='a'*64,manifest_sha256=sha256(raw(manifest)).hexdigest())
        self.current=dict(self.original)
        for k in ('animated_registration_sha256','input_identity_sha256','layer_binding_draft_sha256'):
            manifest['source_addresses'][k]='b'*64
        self.current['character-manifest.json']=raw(manifest)
        self.published=[]
        self.store=SimpleNamespace(read=lambda digest:self.original if digest=='a'*64 else None,
            publish=lambda files:self.published.append(files) or 'b'*64)

    def test_binding_only_update_preserves_original_authority_and_region_scope(self):
        original=deepcopy(self.decision)
        result=apply_current(self.store,self.current,self.decision)
        receipt=json.loads(result['region-exclusion.json'])
        self.assertEqual(receipt['scope_replay']['original_decision'],original)
        self.assertFalse(receipt['scope_replay']['new_human_confirmation'])
        self.assertEqual(self.decision,original)
        self.assertEqual(json.loads(result['skeleton.json'])['slots'],[{'name':'leg'}])
        self.assertEqual(result['images/rest.png'],self.original['images/rest.png'])
        self.assertEqual(json.loads(result['numeric-reference.json'])['animations']['idle'][0]['vertices'],{'leg':[[1,2]]})

    def test_source_bones_layer_slot_texture_and_unknown_source_changes_block(self):
        cases=[('character-manifest.json',lambda d:d['source_addresses'].update(resolved_project_sha256='c'*64)),
               ('character-manifest.json',lambda d:d['source_addresses'].update(new_source='c'*64)),
               ('character-manifest.json',lambda d:d['layers'][0].update(binding_decision={'decision_source':'explicit_selection'})),
               ('skeleton.json',lambda d:d['bones'][0].update(x=5)),
               ('skeleton.json',lambda d:d['slots'][1].update(bone='different')),
               ('skeleton.json',lambda d:d['skins'][0]['attachments']['rest']['rest'].update(x=5))]
        for name,mutate in cases:
            changed=dict(self.current);doc=json.loads(changed[name]);mutate(doc);changed[name]=raw(doc)
            with self.subTest(name=name),self.assertRaises(ValueError):apply_current(self.store,changed,self.decision)
        with self.assertRaises(ValueError):apply_current(self.store,{**self.current,'images/rest.png':b'changed'},self.decision)
        self.assertEqual(self.published,[])

    def test_non_binding_changes_cannot_use_scope_replay(self):
        current=dict(self.original);manifest=json.loads(current['character-manifest.json']);manifest['profile']='different'
        current['character-manifest.json']=raw(manifest)
        with self.assertRaisesRegex(ValueError,'not_binding_update'):apply_current(self.store,current,self.decision)

    def test_invalid_original_review_cannot_be_carried_forward(self):
        with self.assertRaises(ValueError):apply_current(self.store,self.current,{**self.decision,'image_sha256':'c'*64})
        self.assertEqual(self.published,[])
