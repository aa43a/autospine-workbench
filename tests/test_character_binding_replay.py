from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch
from autospine_workbench.targets.character43.binding_continuity import unchanged_layers
from autospine_workbench.automation.character_weighted_review import overview,save,confirmed_layers


@unittest.skipUnless(importlib.util.find_spec('PIL'),'optional Pillow')
class BindingReplayTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        source=fixture();m=json.loads(source['character-manifest.json']);m['source_addresses']={'project':'source'}
        m['layers'][1].update(state='weighted_candidate',binding_decision={'decision_source':'pending','action':'pending'})
        for layer in m['layers']:
            layer.update(missing_region_ids=[],reason_codes=[])
            for r in layer['regions']:r['state']=layer['state']
        source['character-manifest.json']=canonical_bytes(m)
        digest=lambda files:canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()})
        source_sha=digest(source)
        d=dict(schema='autospine.region-exclusion/v1',decision_source='human_confirmation',reversible=True,
            source_bundle_sha256=source_sha,manifest_sha256=sha256(source['character-manifest.json']).hexdigest(),
            layer_id='skirt',region_id='skirt',image_sha256=sha256(source['images/skirt.png']).hexdigest())
        target=apply_batch(source,[d]);target_sha=digest(target)
        self.files={source_sha:source,target_sha:target};self.source=source;self.target=target
        def result(job,sha,files):
            folder=self.root/job;(folder/'runtime').mkdir(parents=True)
            raw=canonical_bytes(dict(bundle_sha256=sha,passed=True))
            (folder/'runtime/report.json').write_bytes(raw)
            value=dict(project_id='p',job_id=job,status='needs_review',artifact_sha256=sha,
                layers=json.loads(files['character-manifest.json'])['layers'],
                runtime=dict(geometry_status='passed',files={'report.json':sha256(raw).hexdigest()}))
            (folder/'result.json').write_bytes(canonical_bytes(value));return value
        self.old=result('job-old',source_sha,source);self.new=result('job-new',target_sha,target)
        review=dict(schema='autospine.character-weighted-review/v1',project_id='p',job_id='job-old',
            artifact_sha256=source_sha,layers_sha256=canonical_sha256(self.old['layers']),
            runtime_sha256=canonical_sha256(self.old['runtime']),accepted_layer_ids=['shirt'],revision=0,
            previous_sha256=None,decision_source='human_review',authority='none',production_authorized=False)
        self.history=self.root/'job-old/weighted-review';self.history.mkdir()
        self.original_review=canonical_bytes(review);(self.history/'000000.json').write_bytes(self.original_review)
        self.manager=SimpleNamespace(root=self.root,_lock=RLock(),_path=lambda j:self.root/j,
            get=lambda *_:deepcopy(self.new),verified_files=lambda *_:target,
            review_file=lambda *_:((self.root/'job-new/runtime/report.json').read_bytes(),'application/json'),
            application=SimpleNamespace(store=SimpleNamespace(read=lambda s:self.files[s])))

    def test_automatic_binding_only_replay_and_local_revoke(self):
        value=overview(self.manager,'p','job-new')
        self.assertEqual(confirmed_layers(self.new,value),{'shirt'})
        self.assertIsNone(value['review']);self.assertFalse(value['replayed_review']['new_human_confirmation'])
        self.assertFalse(value['replayed_review']['whole_character_visual_replayed'])
        from jsonschema import Draft202012Validator
        proof_schema=json.loads((Path(__file__).parents[1]/'schemas/character-binding-replay-v1.schema.json').read_bytes())
        Draft202012Validator(proof_schema).validate(value['replayed_review'])
        from autospine_workbench.automation.character_weighted_replay import read_proof
        self.assertEqual(read_proof(self.manager,value['replay_sha256']),value['replayed_review'])
        body=dict(expected_artifact_sha256=self.new['artifact_sha256'],expected_review_sha256=None,
            expected_replay_sha256=value['replay_sha256'],layer_id='shirt',action='revoke')
        revoked=save(self.manager,'p','job-new',body)
        self.assertEqual(confirmed_layers(self.new,revoked),set())
        self.assertEqual(revoked['review']['accepted_layer_ids'],[])
        self.assertEqual(revoked['review']['revoked_replayed_layer_ids'],['shirt'])
        self.assertEqual((self.history/'000000.json').read_bytes(),self.original_review)
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())
        schema=json.loads((Path(__file__).parents[1]/'schemas/character-weighted-review-v2.schema.json').read_bytes())
        Draft202012Validator(schema).validate(revoked['review'])

    def test_source_revocation_and_stale_proof_do_not_reappear(self):
        value=overview(self.manager,'p','job-new')
        changed=deepcopy(self.new);changed['artifact_sha256']='c'*64
        self.assertEqual(confirmed_layers(changed,value),set())
        doc=json.loads(self.original_review);doc.update(revision=1,previous_sha256=canonical_sha256(doc),accepted_layer_ids=[])
        (self.history/'000001.json').write_bytes(canonical_bytes(doc))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())
        with self.assertRaisesRegex(RuntimeError,'conflict'):
            save(self.manager,'p','job-new',dict(expected_artifact_sha256=self.new['artifact_sha256'],
                expected_review_sha256=None,expected_replay_sha256=value['replay_sha256'],layer_id='shirt',action='revoke'))

    def test_texture_geometry_motion_changes_refuse_continuity(self):
        self.assertEqual(unchanged_layers(self.source,self.target),['shirt'])
        for name in ('images/shirt.png','skeleton.json','numeric-reference.json'):
            target=dict(self.target)
            if name.endswith('.png'):target[name]+=b'changed'
            else:
                doc=json.loads(target[name])
                if name=='skeleton.json':doc['bones'][0]['x']+=1
                else:doc['animations']['idle'][0]['time']=42
                target[name]=canonical_bytes(doc)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'continuity'):
                unchanged_layers(self.source,target)

    def test_failed_new_runtime_never_inherits(self):
        (self.root/'job-new/runtime/report.json').write_bytes(canonical_bytes(dict(bundle_sha256=self.new['artifact_sha256'],passed=False)))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())

    def test_ambiguous_predecessors_do_not_auto_select_a_review(self):
        from shutil import copytree
        copytree(self.root/'job-old',self.root/'job-copy')
        old=deepcopy(self.old);old['job_id']='job-copy'
        (self.root/'job-copy/result.json').write_bytes(canonical_bytes(old))
        review=json.loads(self.original_review);review['job_id']='job-copy'
        (self.root/'job-copy/weighted-review/000000.json').write_bytes(canonical_bytes(review))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())
