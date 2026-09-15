from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest

import test_character_binding_replay as fixtures
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.region_revalidation import revalidate, digest
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch
from autospine_workbench.targets.character43.rebuilt_binding_continuity import unchanged_layers
from autospine_workbench.automation.character_weighted_review import overview, confirmed_layers, save


class RebuiltBindingTests(unittest.TestCase):
    def setUp(self):
        b=fixtures.BindingReplayTests();b.setUp();self.addCleanup(b.doCleanups);self.b=b
        before=b.source;old=b.target
        rebuilt=dict(before);m=json.loads(rebuilt['character-manifest.json'])
        m['source_addresses']['base_bundle_sha256']='3'*64
        rebuilt['character-manifest.json']=raw(m)
        decisions=json.loads(old['final-region-exclusion.json'])['decisions']
        new=apply_batch(rebuilt,revalidate(before,rebuilt,decisions))
        for value,files in ((b.old,old),(b.new,new)):
            value.update(artifact_sha256=digest(files),layers=json.loads(files['character-manifest.json'])['layers'])
            report=raw(dict(bundle_sha256=digest(files),passed=True))
            value['runtime']['files']['report.json']=sha256(report).hexdigest()
            folder=b.root/value['job_id'];(folder/'runtime/report.json').write_bytes(report)
            (folder/'result.json').write_bytes(raw(value))
        review=json.loads(b.original_review)
        review.update(artifact_sha256=b.old['artifact_sha256'],layers_sha256=canonical_sha256(b.old['layers']),
                      runtime_sha256=canonical_sha256(b.old['runtime']))
        b.original_review=raw(review);(b.history/'000000.json').write_bytes(b.original_review)
        b.source=old;b.target=new;b.files={digest(old):old,digest(new):new}
        b.manager.verified_files=lambda *_:new

    def test_rebuilt_scope_and_local_revoke_preserve_original_history(self):
        b=self.b;value=overview(b.manager,'p','job-new')
        self.assertEqual(confirmed_layers(b.new,value),{'shirt'})
        self.assertIsNone(value['review'])
        from jsonschema import Draft202012Validator
        schema=json.loads((Path(__file__).parents[1]/'schemas/character-binding-replay-v4.schema.json').read_bytes())
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(value['replayed_review'])
        self.assertFalse(value['replayed_review']['new_human_confirmation'])
        revoked=save(b.manager,'p','job-new',dict(action='revoke',layer_id='shirt',expected_review_sha256=None,
            expected_artifact_sha256=b.new['artifact_sha256'],expected_replay_sha256=value['replay_sha256']))
        self.assertEqual(confirmed_layers(b.new,revoked),set())
        self.assertEqual((b.history/'000000.json').read_bytes(),b.original_review)
        self.assertEqual(confirmed_layers(b.new,overview(b.manager,'p','job-new')),set())

    def test_original_revocation_invalidates_proof_and_stale_write(self):
        b=self.b;value=overview(b.manager,'p','job-new')
        original=json.loads(b.original_review)
        revoked=dict(original,revision=1,previous_sha256=canonical_sha256(original),accepted_layer_ids=[])
        (b.history/'000001.json').write_bytes(raw(revoked))
        self.assertEqual(confirmed_layers(b.new,overview(b.manager,'p','job-new')),set())
        with self.assertRaisesRegex(RuntimeError,'conflict'):
            save(b.manager,'p','job-new',dict(action='revoke',layer_id='shirt',expected_review_sha256=None,
                expected_artifact_sha256=b.new['artifact_sha256'],expected_replay_sha256=value['replay_sha256']))

    def test_changed_scope_cannot_inherit(self):
        b=self.b
        self.assertEqual(unchanged_layers(b.source,b.target),['shirt'])
        for kind in ('texture','bones','weights','trajectory','source','receipt','layer'):
            new=dict(b.target)
            if kind=='texture':new['images/shirt.png']+=b'changed'
            elif kind in ('bones','weights'):
                doc=json.loads(new['skeleton.json'])
                if kind=='bones':doc['bones'][0]['x']+=1
                else:doc['skins'][0]['attachments']['shirt']['shirt']['vertices'][0]+=1
                new['skeleton.json']=raw(doc)
            elif kind=='trajectory':
                ref=json.loads(new['numeric-reference.json']);ref['animations']['idle'][0]['time']+=1
                new['numeric-reference.json']=raw(ref)
            elif kind=='receipt':
                receipt=json.loads(new['final-region-exclusion.json']);receipt['decisions'][0]['scope_replay']['new_human_confirmation']=True
                new['final-region-exclusion.json']=raw(receipt)
            else:
                manifest=json.loads(new['character-manifest.json'])
                if kind=='source':manifest['source_addresses']['project']='different'
                else:manifest['layers'][1]['name']='changed'
                new['character-manifest.json']=raw(manifest)
            with self.subTest(kind=kind):self.assertEqual(unchanged_layers(b.source,new),[])

    def test_failed_new_runtime_does_not_inherit(self):
        b=self.b
        (b.root/'job-new/runtime/report.json').write_bytes(raw(dict(bundle_sha256=b.new['artifact_sha256'],passed=False)))
        self.assertEqual(confirmed_layers(b.new,overview(b.manager,'p','job-new')),set())

    def test_ambiguous_sources_never_select_one_approval(self):
        from shutil import copytree
        b=self.b;copytree(b.root/'job-old',b.root/'job-copy')
        old=dict(b.old,job_id='job-copy');(b.root/'job-copy/result.json').write_bytes(raw(old))
        review=json.loads(b.original_review);review['job_id']='job-copy'
        (b.root/'job-copy/weighted-review/000000.json').write_bytes(raw(review))
        self.assertEqual(confirmed_layers(b.new,overview(b.manager,'p','job-new')),set())

    def test_revocation_during_scope_check_is_not_published(self):
        from unittest.mock import patch
        b=self.b
        def checking(*args):
            original=json.loads(b.original_review)
            revoked=dict(original,revision=1,previous_sha256=canonical_sha256(original),accepted_layer_ids=[])
            (b.history/'000001.json').write_bytes(raw(revoked))
            return ['shirt']
        with patch('autospine_workbench.automation.character_rebuilt_binding_replay.unchanged_layers',checking):
            self.assertEqual(confirmed_layers(b.new,overview(b.manager,'p','job-new')),set())
