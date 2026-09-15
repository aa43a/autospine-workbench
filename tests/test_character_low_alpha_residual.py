from hashlib import sha256
import json
from types import SimpleNamespace
import unittest

from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.automation.character_residual_defaults import apply as automate
from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png
from autospine_workbench.targets.character43.low_alpha_residual import propose, PROFILE
from autospine_workbench.targets.character43.region_exclusion import apply
from autospine_workbench.targets.character43.final_region_exclusion import apply_batch


def fixture(alpha=7):
    names=['a', 'a-residual', 'b', 'b-residual']
    skeleton=dict(slots=[dict(name=n) for n in names], skins=[dict(attachments={
        n:{n:dict(path=n,triangles=[0,1,2])} for n in names})],animations={'idle':{}})
    manifest=dict(layers=[dict(layer_id=n,state='partial',reason_codes=['static_reference_not_bound'],
        missing_region_ids=[],regions=[dict(region_id=n,state='weighted_candidate'),
        dict(region_id=n+'-residual',state='static_reference')]) for n in ('a','b')])
    files={'skeleton.json':raw(skeleton),'editor/skeleton.json':raw(skeleton),
           'character-manifest.json':raw(manifest),'skeleton.atlas':b'unchanged atlas'}
    for n in names:files['images/'+n+'.png']=encode_rgba_png(RgbaImage(1,1,bytes([10,20,30,alpha])))
    files['numeric-reference.json']=raw(dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        animations={'idle':[dict(time=t,vertices={n:[[0,0],[1,0],[0,1]] for n in names}) for t in (0,1)]}))
    return files


class LowAlphaTests(unittest.TestCase):
    def test_boundary_and_empty_are_not_excluded(self):
        for alpha in (0,8,255):self.assertEqual(propose(fixture(alpha)),[])
        self.assertEqual(len(propose(fixture())),2)

    def test_requires_residual_and_weighted_peer(self):
        files=fixture();manifest=json.loads(files['character-manifest.json'])
        manifest['layers'][0]['regions'][0]['state']='static_reference'
        manifest['layers'][1]['layer_id']='different'
        files['character-manifest.json']=raw(manifest)
        self.assertEqual(propose(files),[])

    def test_source_and_policy_tampering_rejected(self):
        files=fixture();decision=propose(files)[0]
        for key,value in [('source_bundle_sha256','0'*64),('max_alpha',8),('policy_id','unknown'),
                          ('region_id','a'),('image_sha256','0'*64),('reversible',False)]:
            with self.subTest(key=key),self.assertRaises(ValueError):apply(files,{**decision,key:value})
        files['unrelated-source.txt']=b'changed'
        with self.assertRaises(ValueError):apply(files,decision)

    def test_batch_preserves_textures_and_surviving_animation(self):
        files=fixture();before=dict(files);output=apply_batch(files,propose(files))
        self.assertEqual(files,before)
        for name in files:
            if name.endswith('.png'):self.assertEqual(output[name],files[name])
        original=json.loads(files['numeric-reference.json'])['animations']['idle']
        actual=json.loads(output['numeric-reference.json'])['animations']['idle']
        for old,new in zip(original,actual):
            self.assertEqual(new,dict(time=old['time'],vertices={n:old['vertices'][n] for n in ('a','b')}))
        receipt=json.loads(output['final-region-exclusion.json'])
        self.assertFalse(receipt['production_authorized'])
        self.assertTrue(all(d['decision_source']=='policy_auto' for d in receipt['decisions']))
        self.assertEqual(len(receipt['decisions']),2)
        self.assertTrue(json.loads(output['deformation.json'])['passed'])

    def test_disabled_and_explicit_recipe_preserved(self):
        files=fixture();published=[]
        store=SimpleNamespace(read=lambda _:files,publish=lambda output:published.append(output) or 'new')
        manager=SimpleNamespace(application=SimpleNamespace(store=store))
        result=dict(artifact_sha256='old',manifest=json.loads(files['character-manifest.json']))
        for request in ({},{'residual_auto_profile':'preserve'}):
            self.assertIs(automate(manager,request,result),result)
        automatic=automate(manager,{'residual_auto_profile':PROFILE},result)
        self.assertEqual(automatic['residual_defaults']['excluded_region_ids'],['a-residual','b-residual'])
        self.assertEqual(len(published),1)
        files['final-region-exclusion.json']=b'preserved human recipe'
        self.assertIs(automate(manager,{'residual_auto_profile':PROFILE},result),result)
        self.assertEqual(len(published),1)
