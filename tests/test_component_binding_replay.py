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
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch
from autospine_workbench.targets.character43.component_mount_candidate import generate
from autospine_workbench.targets.character43.component_binding_continuity import unchanged_layers
from autospine_workbench.automation.character_weighted_review import overview,save,confirmed_layers


@unittest.skipUnless(importlib.util.find_spec('PIL'),'optional Pillow')
class ComponentBindingReplayTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        source=fixture();doc=json.loads(source['skeleton.json'])
        doc['slots'].append(dict(name='noise',attachment='noise',bone='root'))
        doc['skins'][0]['attachments']['noise']={'noise':deepcopy(doc['skins'][0]['attachments']['skirt']['skirt'])}
        source['skeleton.json']=canonical_bytes(doc)
        editor=deepcopy(doc);editor['skeleton']['images']='./images/';source['editor/skeleton.json']=canonical_bytes(editor)
        source['numeric-reference.json']=canonical_bytes(dict(skeleton_sha256=sha256(source['skeleton.json']).hexdigest(),
            animations={'idle':[dict(time=i/8,vertices=sample(doc,'idle',i/8)[0]) for i in range(17)]}))
        manifest=json.loads(source['character-manifest.json']);manifest['source_addresses']={'project':'source'}
        manifest['layers'].append(dict(layer_id='noise',state='static_reference',regions=[dict(region_id='noise')]))
        manifest['layers'][1].update(state='weighted_candidate',binding_decision=dict(action='pending',decision_source='pending'))
        for layer in manifest['layers']:
            layer.update(missing_region_ids=[],reason_codes=[])
            for region in layer['regions']:region['state']=layer['state']
        source['character-manifest.json']=canonical_bytes(manifest)
        digest=lambda f:canonical_sha256({n:sha256(b).hexdigest() for n,b in f.items()})
        source_sha=digest(source)
        middle=apply_batch(source,[dict(schema='autospine.region-exclusion/v1',decision_source='human_confirmation',reversible=True,
            source_bundle_sha256=source_sha,manifest_sha256=sha256(source['character-manifest.json']).hexdigest(),
            layer_id='noise',region_id='noise',image_sha256=sha256(source['images/skirt.png']).hexdigest())])
        target,_=generate(middle,'skirt',['root','chest']);self.middle=middle;self.target=target
        self.files={digest(f):f for f in [source,middle,target]}
        def result(job,files):
            folder=self.root/job;(folder/'runtime').mkdir(parents=True)
            raw=canonical_bytes(dict(bundle_sha256=digest(files),passed=True));(folder/'runtime/report.json').write_bytes(raw)
            value=dict(project_id='p',job_id=job,status='needs_review',artifact_sha256=digest(files),
                layers=json.loads(files['character-manifest.json'])['layers'],
                runtime=dict(geometry_status='passed',files={'report.json':sha256(raw).hexdigest()}))
            (folder/'result.json').write_bytes(canonical_bytes(value));return value
        self.old=result('job-old',source);self.mid=result('job-mid',middle);self.new=result('job-new',target)
        review=dict(schema='autospine.character-weighted-review/v1',project_id='p',job_id='job-old',artifact_sha256=source_sha,
            layers_sha256=canonical_sha256(self.old['layers']),runtime_sha256=canonical_sha256(self.old['runtime']),
            accepted_layer_ids=['shirt'],revision=0,previous_sha256=None,decision_source='human_review',authority='none',production_authorized=False)
        self.history=self.root/'job-old/weighted-review';self.history.mkdir();self.original=canonical_bytes(review)
        (self.history/'000000.json').write_bytes(self.original)
        self.manager=SimpleNamespace(root=self.root,_lock=RLock(),_path=lambda j:self.root/j,get=lambda *_:deepcopy(self.new),verified_files=lambda *_:target,
            review_file=lambda *_:((self.root/'job-new/runtime/report.json').read_bytes(),'application/json'),
            application=SimpleNamespace(store=SimpleNamespace(read=lambda s:self.files[s])))

    def test_two_steps_preserve_original_review_and_allow_local_revoke(self):
        value=overview(self.manager,'p','job-new')
        self.assertEqual(confirmed_layers(self.new,value),{'shirt'})
        self.assertEqual(value['replayed_review']['schema'],'autospine.character-binding-replay/v2')
        self.assertIsNone(value['replayed_review']['source_review_sha256'])
        self.assertTrue(value['replayed_review']['source_replay_sha256'])
        from jsonschema import Draft202012Validator
        Draft202012Validator(json.loads((Path(__file__).parents[1]/'schemas/character-binding-replay-v2.schema.json').read_bytes())).validate(value['replayed_review'])
        revoked=save(self.manager,'p','job-new',dict(expected_artifact_sha256=self.new['artifact_sha256'],expected_review_sha256=None,
            expected_replay_sha256=value['replay_sha256'],layer_id='shirt',action='revoke'))
        self.assertEqual(confirmed_layers(self.new,revoked),set())
        self.assertEqual((self.history/'000000.json').read_bytes(),self.original)

    def test_original_and_intermediate_revocations_are_honored(self):
        original=json.loads(self.original);original.update(revision=1,previous_sha256=canonical_sha256(original),accepted_layer_ids=[])
        (self.history/'000001.json').write_bytes(canonical_bytes(original))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())
        (self.history/'000001.json').unlink()
        mid=self.mid;root=self.root/'job-mid/weighted-review';root.mkdir()
        override=dict(schema='autospine.character-weighted-review/v2',project_id='p',job_id=mid['job_id'],artifact_sha256=mid['artifact_sha256'],
            layers_sha256=canonical_sha256(mid['layers']),runtime_sha256=canonical_sha256(mid['runtime']),accepted_layer_ids=[],
            revoked_replayed_layer_ids=['shirt'],replay_sha256=None,revision=0,previous_sha256=None,decision_source='human_review',authority='none',production_authorized=False)
        (root/'000000.json').write_bytes(canonical_bytes(override))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())

    def test_unmodified_scope_rejects_texture_bone_order_and_motion_changes(self):
        self.assertEqual(unchanged_layers(self.middle,self.target),['noise','shirt'])
        for kind in ['texture','bone','order','motion','atlas']:
            changed=dict(self.target)
            if kind=='texture':changed['images/shirt.png']+=b'changed'
            elif kind=='atlas':changed['skeleton.atlas']+=b'new override'
            elif kind=='motion':
                ref=json.loads(changed['numeric-reference.json']);ref['animations']['idle'][0]['time']=42;changed['numeric-reference.json']=canonical_bytes(ref)
            else:
                doc=json.loads(changed['skeleton.json'])
                if kind=='bone':doc['bones'][0]['x']+=1
                else:doc['slots'].reverse()
                changed['skeleton.json']=canonical_bytes(doc)
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'continuity'):unchanged_layers(self.middle,changed)

    def test_ambiguous_predecessor_and_failed_current_runtime_do_not_replay(self):
        from shutil import copytree
        copytree(self.root/'job-mid',self.root/'job-copy')
        duplicate=dict(self.mid,job_id='job-copy')
        (self.root/'job-copy/result.json').write_bytes(canonical_bytes(duplicate))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())
        (self.root/'job-new/runtime/report.json').write_bytes(canonical_bytes(dict(bundle_sha256=self.new['artifact_sha256'],passed=False)))
        self.assertEqual(confirmed_layers(self.new,overview(self.manager,'p','job-new')),set())
