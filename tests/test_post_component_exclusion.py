"""Post-component decisions stay separate and preserve actual prior bindings."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.component_mount_candidate import generate
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch
from autospine_workbench.targets.character43.binding_continuity import unchanged_layers
from autospine_workbench.automation.character_final_regions import save,overview,apply_saved
from autospine_workbench.automation.character_weighted_review import overview as bindings,confirmed_layers


def digest(files):return canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()})


def schema_check(name,value):
    from jsonschema import Draft202012Validator
    schema=json.loads((Path(__file__).parents[1]/'schemas'/name).read_bytes())
    Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(value)


@unittest.skipUnless(importlib.util.find_spec('PIL'),'optional Pillow')
class PostComponentExclusionTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image,ImageDraw
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        base=fixture();image=Image.new('RGBA',(80,100));draw=ImageDraw.Draw(image)
        draw.rectangle((5,5,20,25),fill=(255,0,0,255));image.putpixel((70,90),(1,2,3,7))
        stream=BytesIO();image.save(stream,format='PNG');base['images/skirt.png']=stream.getvalue()
        m=json.loads(base['character-manifest.json']);m['source_addresses']={'project':'p'}
        m['layers'][1]['state']='weighted_candidate'
        for layer in m['layers']:
            layer.update(reason_codes=[],missing_region_ids=[],binding_decision={'action':'pending','decision_source':'pending'})
            for r in layer['regions']:r['state']=layer['state']
        base['character-manifest.json']=canonical_bytes(m)
        self.source,_=generate(base,'skirt',['root','chest']);key='skirt-unbound-residual'
        self.decision=dict(schema='autospine.region-exclusion/v1',decision_source='human_confirmation',reversible=True,
            source_bundle_sha256=digest(self.source),manifest_sha256=sha256(self.source['character-manifest.json']).hexdigest(),
            layer_id='skirt',region_id=key,image_sha256=sha256(self.source['images/'+key+'.png']).hexdigest())
        self.target=apply_batch(self.source,[self.decision],after_components=True)
        store={digest(f):f for f in [base,self.source,self.target]}
        def result(job,files):
            folder=self.root/job;(folder/'runtime').mkdir(parents=True)
            raw=canonical_bytes(dict(bundle_sha256=digest(files),passed=True));(folder/'runtime/report.json').write_bytes(raw)
            value=dict(project_id='p',job_id=job,status='needs_review',artifact_sha256=digest(files),
                layers=json.loads(files['character-manifest.json'])['layers'],
                runtime=dict(geometry_status='passed',files={'report.json':sha256(raw).hexdigest()}))
            (folder/'result.json').write_bytes(canonical_bytes(value));(folder/'request.json').write_text('{}');return value
        self.old=result('job-old',self.source);self.new=result('job-new',self.target)
        self.manager=SimpleNamespace(root=self.root,_lock=RLock(),projects=SimpleNamespace(get_project=lambda _:None),
            _path=lambda j:self.root/j,get=lambda _,j:self.old if j=='job-old' else self.new,verified_files=lambda *_:self.source,
            review_file=lambda *_:((self.root/'job-new/runtime/report.json').read_bytes(),'application/json'),
            application=SimpleNamespace(store=SimpleNamespace(read=lambda s:store[s],publish=digest)))
        self.review=dict(schema='autospine.character-weighted-review/v2',project_id='p',job_id='job-old',artifact_sha256=digest(self.source),
            layers_sha256=canonical_sha256(self.old['layers']),runtime_sha256=canonical_sha256(self.old['runtime']),
            accepted_layer_ids=['shirt'],revoked_replayed_layer_ids=[],revision=0,previous_sha256=None,
            decision_source='human_review',authority='none',production_authorized=False)
        folder=self.root/'job-old/weighted-review';folder.mkdir();(folder/'000000.json').write_bytes(canonical_bytes(self.review))

    def test_other_bindings_and_pixels_remain_exact(self):
        self.assertIn('shirt',unchanged_layers(self.source,self.target,after_components=True))
        report=json.loads(self.target['component-mount.json'])
        self.assertEqual(report['excluded_pixels'],1);self.assertEqual(len(report['parts']),1)
        self.assertEqual(self.target['pre-exclusion-evidence/component-mount.json'],self.source['component-mount.json'])
        value=bindings(self.manager,'p','job-new');self.assertEqual(confirmed_layers(self.new,value),{'shirt'})
        self.assertEqual(value['replayed_review']['schema'],'autospine.character-binding-replay/v3')
        schema_check('character-binding-replay-v3.schema.json',value['replayed_review'])
        schema_check('final-region-exclusion-v2.schema.json',json.loads(self.target['final-region-exclusion.json']))
        changed=dict(self.target);changed['images/shirt.png']+=b'changed'
        with self.assertRaises(ValueError):unchanged_layers(self.source,changed,after_components=True)
        self.review.update(revision=1,previous_sha256=canonical_sha256(self.review),accepted_layer_ids=[])
        (self.root/'job-old/weighted-review/000001.json').write_bytes(canonical_bytes(self.review))
        self.assertEqual(confirmed_layers(self.new,bindings(self.manager,'p','job-new')),set())

    def test_post_history_recovery_revoke_and_source_guard(self):
        body=dict(action='replace',expected_head_sha256=None,job_id='job-old',expected_artifact_sha256=digest(self.source),
            regions=[dict(layer_id='skirt',region_id='skirt-unbound-residual')])
        with self.assertRaisesRegex(RuntimeError,'stage_required'):save(self.manager,'p',body)
        v=save(self.manager,'p',body,stage='after_components')
        schema_check('character-final-regions-v2.schema.json',v['review'])
        self.assertEqual(overview(self.manager,'p',stage='after_components'),v)
        self.assertIsNone(overview(self.manager,'p')['head_sha256'])
        request=dict(project_id='p',post_component_regions_sha256=v['head_sha256'])
        result=apply_saved(self.manager,request,self.old,stage='after_components')
        self.assertEqual(result['artifact_sha256'],digest(self.target))
        with self.assertRaisesRegex(RuntimeError,'source_changed'):apply_saved(self.manager,request,self.new,stage='after_components')
        revoked=save(self.manager,'p',dict(action='revoke',expected_head_sha256=v['head_sha256']),stage='after_components')
        self.assertFalse(revoked['active']);self.assertIsNone(overview(self.manager,'p')['head_sha256'])
