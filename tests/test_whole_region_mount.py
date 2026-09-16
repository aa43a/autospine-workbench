from io import BytesIO
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image, ImageDraw
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.component_mount_candidate import generate
from autospine_workbench.automation.character_component_mounts import _valid


class WholeRegionMountTests(unittest.TestCase):
    def test_v2_reproduces_default_stage_before_source_comparison(self):
        from autospine_workbench.automation.character_component_mounts import apply_saved
        files,d,_=self.fixture()
        manager=SimpleNamespace(application=SimpleNamespace(store=SimpleNamespace(
            read=lambda digest:files, publish=lambda output:'published')))
        current=dict(head_sha256='head',active=True,review=dict(decision=d,allowed_parents=['root','chest']))
        initial=dict(artifact_sha256='before-defaults',manifest={})
        staged=dict(artifact_sha256=d['source_bundle_sha256'],manifest={})
        with patch('autospine_workbench.automation.character_component_mounts.overview',return_value=current), \
             patch('autospine_workbench.automation.character_residual_defaults.apply',return_value=staged) as defaults:
            result=apply_saved(manager,dict(project_id='test',component_mounts_sha256='head'),initial)
        defaults.assert_called_once_with(manager,dict(project_id='test',component_mounts_sha256='head'),initial)
        self.assertEqual(result['artifact_sha256'],'published')

    def fixture(self):
        files=fixture();image=Image.new('RGBA',(80,100));ImageDraw.Draw(image).rectangle((5,5,20,20),fill=(9,20,40,255))
        image.putpixel((60,60),(10,20,30,7));buf=BytesIO();image.save(buf,format='PNG');files['images/skirt.png']=buf.getvalue()
        manifest=json.loads(files['character-manifest.json'])
        for layer in manifest['layers']:
            for region in layer['regions']:region['state']=layer['state']
        files['character-manifest.json']=canonical_bytes(manifest)
        _,r=generate(files,'skirt',['root','chest'])
        d=dict(schema='autospine.component-mount-decision/v2',source_bundle_sha256=r['source_bundle_sha256'],
            source_region_id='skirt',plan_sha256=r['plan_sha256'],decision_source='human_confirmation',reversible=True,
            parents={'component-0000':'chest'},residual_parent='chest')
        return files,d,image

    def test_all_pixels_follow_confirmed_parent_without_loss(self):
        files,d,image=self.fixture();out,r=generate(files,'skirt',['root','chest'],d)
        self.assertTrue(r['geometry_passed']);self.assertFalse(r['parent_review_required'])
        self.assertEqual({p['proposed_parent'] for p in r['parts']},{'chest'})
        reconstructed=Image.new('RGBA',image.size)
        for p in r['parts']:
            crop=Image.open(BytesIO(out['images/'+p['region_id']+'.png']))
            reconstructed.alpha_composite(crop,tuple(p['bbox'][:2]))
        self.assertEqual(reconstructed.tobytes(),image.tobytes())
        layer=next(l for l in json.loads(out['character-manifest.json'])['layers'] if l['layer_id']=='skirt')
        self.assertEqual(layer['state'],'weighted_candidate')
        self.assertTrue(all(p['state']=='weighted_candidate' for p in layer['regions']))
        self.assertTrue(_valid(dict(decision=d,allowed_parents=['root','chest'],build_options={})))

    def test_old_decision_keeps_residual_and_mixed_parent_is_rejected(self):
        files,d,_=self.fixture();old={k:v for k,v in d.items() if k!='residual_parent'};old['schema']='autospine.component-mount-decision/v1'
        _,r=generate(files,'skirt',['root','chest'],old)
        self.assertEqual(r['parts'][-1]['reason_code'],'small_components_retained')
        d['residual_parent']='root'
        with self.assertRaisesRegex(ValueError,'residual_scope'):generate(files,'skirt',['root','chest'],d)
        self.assertFalse(_valid(dict(decision=d,allowed_parents=['root','chest'],build_options={})))
