from copy import deepcopy
from io import BytesIO
import importlib.util
import json
import unittest
from pathlib import Path
from test_character_skirt_candidate import fixture
from autospine_workbench.asset.planning.component_mount import partition
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.component_mount_candidate import generate
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.resolved_project import canonical_sha256


class ComponentMountPartitionTests(unittest.TestCase):
    def test_four_components_and_noise_are_disjoint_and_exhaustive(self):
        alpha=bytearray(80*100)
        for x0,y0 in [(5,5),(60,5),(5,70),(60,70)]:
            for y in range(y0,y0+15):
                for x in range(x0,x0+12):alpha[y*80+x]=255
        alpha[40*80+40]=7
        result=partition(alpha,80,100,{'head':[40,10],'chest':[40,80]})
        groups=result['regions'];self.assertEqual(len(groups),4)
        self.assertEqual([g['proposed_parent'] for g in groups],['head','head','chest','chest'])
        self.assertEqual(result['residual_pixels'],[3240])
        self.assertEqual(sum(len(g['pixels']) for g in groups)+1,result['visible_pixel_count'])
        mirrored=partition(bytearray(v for y in range(100) for v in reversed(alpha[y*80:y*80+80])),80,100,{'head':[40,10],'chest':[40,80]})
        self.assertEqual([g['proposed_parent'] for g in mirrored['regions']],['head','head','chest','chest'])

    def test_bad_dimensions_and_nonfinite_anchors_fail(self):
        with self.assertRaises(ValueError):partition(b'\xff',80,100,{'head':[0,0]})
        with self.assertRaises(ValueError):partition(b'\xff',1,1,{'head':[float('nan'),0]})


@unittest.skipUnless(importlib.util.find_spec('PIL'),'optional Pillow')
class ComponentMountCandidateTests(unittest.TestCase):
    def test_full_scene_keeps_other_motion_and_visible_pixels(self):
        from PIL import Image,ImageDraw
        files=fixture();image=Image.new('RGBA',(80,100));draw=ImageDraw.Draw(image)
        for x0,y0 in [(5,5),(60,5),(5,70),(60,70)]:draw.rectangle((x0,y0,x0+11,y0+14),fill=(90,20,50,255))
        image.putpixel((40,40),(1,2,3,7));stream=BytesIO();image.save(stream,format='PNG');files['images/skirt.png']=stream.getvalue()
        manifest=json.loads(files['character-manifest.json'])
        for layer in manifest['layers']:
            for region in layer['regions']:region['state']=layer['state']
        files['character-manifest.json']=canonical_bytes(manifest);before=deepcopy(files)
        output,report=generate(files,'skirt',['root','chest'])
        self.assertEqual(files,before);self.assertTrue(report['geometry_passed']);self.assertFalse(report['selected'])
        self.assertEqual(report['covered_pixels'],721);self.assertEqual(len(report['parts']),5)
        rebuilt=Image.new('RGBA',image.size)
        for row in report['parts']:
            crop=Image.open(BytesIO(output['images/'+row['region_id']+'.png']))
            rebuilt.alpha_composite(crop,tuple(row['bbox'][:2]))
        self.assertEqual(rebuilt.tobytes(),image.tobytes())
        for old,new in zip(read(files)['animations']['idle'],read(output)['animations']['idle']):
            self.assertEqual(old['vertices']['shirt'],new['vertices']['shirt'])
        self.assertEqual(output['images/skirt.png'],files['images/skirt.png'])
        skeleton=json.loads(output['skeleton.json'])
        self.assertEqual(skeleton['slots'][-1]['name'],'shirt')
        self.assertEqual(skeleton['animations'],json.loads(files['skeleton.json'])['animations'])
        self.assertEqual(generate(files,'skirt',['root','chest'])[0],output)
        from autospine_workbench.targets.character43.component_mount_review import render
        from hashlib import sha256
        capture=dict(bundle_sha256=canonical_sha256({n:sha256(b).hexdigest() for n,b in output.items()}),authority='none',
            results=[dict(animation='idle',index=0,time=0)],screenshots=[dict(animation='idle',index=0,file='frames/idle-0.png')])
        self.assertIn(b'type="range"',render(output,capture))
        with self.assertRaisesRegex(ValueError,'capture_source'):render(output,dict(capture,bundle_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'capture_path'):
            render(output,dict(capture,screenshots=[dict(animation='idle',index=0,file='../unsafe.png')]))
        decision=dict(schema='autospine.component-mount-decision/v1',source_bundle_sha256=report['source_bundle_sha256'],
            source_region_id='skirt',plan_sha256=report['plan_sha256'],decision_source='human_confirmation',reversible=True,
            parents={r['component_id']:'chest' for r in report['parts'] if r['component_id']!='unbound-residual'})
        reviewed,accepted=generate(files,'skirt',['root','chest'],decision)
        self.assertFalse(accepted['parent_review_required']);self.assertFalse(accepted['selected'])
        self.assertIn('component-mount-decision.json',reviewed)
        from jsonschema import Draft202012Validator
        for filename,document in [('component-mount-decision-v1.schema.json',decision),('character-component-mount-v1.schema.json',accepted)]:
            schema=json.loads((Path(__file__).parents[1]/'schemas'/filename).read_bytes())
            Draft202012Validator(schema).validate(document)
        with self.assertRaisesRegex(ValueError,'decision_source'):
            generate(files,'skirt',['root','chest'],dict(decision,plan_sha256='a'*64))

    def test_nonstatic_or_unknown_parent_is_blocked(self):
        files=fixture()
        manifest=json.loads(files['character-manifest.json'])
        for layer in manifest['layers']:
            for region in layer['regions']:region['state']=layer['state']
        files['character-manifest.json']=canonical_bytes(manifest)
        with self.assertRaises(ValueError):generate(files,'shirt',['chest'])
        with self.assertRaises(ValueError):generate(files,'skirt',['unknown'])
