from hashlib import sha256
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.automation.motion_related_evidence import inspect,bundle_digest


class RelatedEvidenceTests(unittest.TestCase):
    def setUp(self):
        addresses={k:'a'*64 for k in ('resolved_project_sha256','input_identity_sha256',
            'skeleton_candidate_sha256','layer_bindings_sha256','layer_binding_draft_sha256')}
        self.base={'character-manifest.json':raw(dict(source_addresses=addresses,source_character_sha256='b'*64,target='4.3.26'))}
        self.files={**self.base,'skeleton.json':b'{}'}
        self.files['numeric-reference.json']=raw(dict(skeleton_sha256=sha256(b'{}').hexdigest(),
            animations={'external-motion':[dict(time=0),dict(time=1)]}))
        self.request=dict(character_sha256=bundle_digest(self.base),motion_identity={'motion_ir_sha256':'c'*64})
        self.receipt=dict(candidate_bundle_sha256=bundle_digest(self.files),source_identity=self.request['motion_identity'],
                          sampled_frames=2,authority='none',selected=False,production_authorized=False)
        self.runtime=dict(bundle_sha256=bundle_digest(self.files),authority='none',production_authorized=False,
            passed=True,runtime_sha256='d'*64,runtime_version='4.3.13',
            results=[dict(animation='external-motion',index=i,time=i) for i in range(2)])
        self.visual=dict(artifact_sha256=bundle_digest(self.files),source_motion_ir_sha256='c'*64,
            technical_override=False,production_authorized=False,applies_to_other_candidates=False)

    def check(self):return inspect(self.request,self.base,self.files,self.receipt,self.runtime,self.visual)

    def test_exact_relation_keeps_versions_and_visual_scope(self):
        r=self.check();self.assertEqual(r['target_version'],'4.3.26');self.assertEqual(r['runtime_version'],'4.3.13')
        self.assertFalse(r['selected']);self.assertEqual(r['visual'],self.visual)

    def test_mutated_asset_rejected(self):
        self.files['skeleton.json']=b'{ }'
        with self.assertRaisesRegex(ValueError,'bundle_identity'):self.check()

    def test_direct_character_bundle_provenance_is_valid(self):
        import json
        manifest=json.loads(self.files['character-manifest.json'])
        manifest['source_character_sha256']=self.request['character_sha256']
        self.files['character-manifest.json']=raw(manifest)
        digest=bundle_digest(self.files)
        self.receipt['candidate_bundle_sha256']=digest
        self.runtime['bundle_sha256']=digest;self.visual['artifact_sha256']=digest
        self.assertEqual(self.check()['character_sha256'],self.request['character_sha256'])
        manifest['source_character_sha256']='f'*64
        self.files['character-manifest.json']=raw(manifest)
        self.receipt['candidate_bundle_sha256']=bundle_digest(self.files)
        with self.assertRaisesRegex(ValueError,'character_sources'):self.check()

    def test_other_motion_rejected(self):
        self.receipt['source_identity']={'motion_ir_sha256':'e'*64}
        with self.assertRaisesRegex(ValueError,'motion_identity'):self.check()

    def test_changed_binding_even_with_new_valid_bundle_rejected(self):
        import json
        m=json.loads(self.files['character-manifest.json']);m['source_addresses']['layer_bindings_sha256']='e'*64
        self.files['character-manifest.json']=raw(m);self.receipt['candidate_bundle_sha256']=bundle_digest(self.files)
        with self.assertRaisesRegex(ValueError,'character_sources'):self.check()

    def test_missing_or_reordered_runtime_samples_rejected(self):
        self.runtime['results'].reverse()
        with self.assertRaisesRegex(ValueError,'runtime_samples'):self.check()

    def test_baseline_acceptance_cannot_transfer(self):
        self.visual['artifact_sha256']=self.request['character_sha256']
        with self.assertRaisesRegex(ValueError,'visual_identity'):self.check()

    def test_runtime_failure_not_overridden_by_visual(self):
        self.runtime['passed']=False
        with self.assertRaisesRegex(ValueError,'runtime_evidence'):self.check()
