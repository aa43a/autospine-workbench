from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_character_skirt_candidate import fixture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.region_mount_candidate import generate
from autospine_workbench.automation.character_region_mounts import save,overview,apply_saved


class RegionMountTests(unittest.TestCase):
    def source(self):
        files=fixture();doc=json.loads(files['skeleton.json'])
        doc['bones'][-1].update(rotation=23,x=9,scaleX=1.2,scaleY=.8)
        doc['animations']['idle']['bones']['chest']={'rotate':[{'time':0,'value':0},{'time':1,'value':25}]}
        files['skeleton.json']=canonical_bytes(doc)
        ref=json.loads(files['numeric-reference.json'])
        ref['skeleton_sha256']=sha256(files['skeleton.json']).hexdigest()
        for f in ref['animations']['idle']:f['vertices']=sample(doc,'idle',f['time'])[0]
        files['numeric-reference.json']=canonical_bytes(ref)
        manifest=json.loads(files['character-manifest.json'])
        for layer in manifest['layers']:
            for region in layer['regions']:region['state']=layer['state']
        files['character-manifest.json']=canonical_bytes(manifest)
        d=dict(schema='autospine.region-mount-decision/v1',source_bundle_sha256=canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()}),
               parents={'skirt':'chest'},decision_source='human_confirmation',reversible=True)
        return files,d

    def test_affine_setup_texture_and_unselected_motion_preserved(self):
        files,d=self.source();before=deepcopy(files);out,r=generate(files,d)
        self.assertEqual(files,before);self.assertTrue(r['geometry_passed']);self.assertEqual(out,generate(files,d)[0])
        a=json.loads(files['skeleton.json']);b=json.loads(out['skeleton.json'])
        self.assertEqual(a['slots'],b['slots']);self.assertEqual(a['animations'],b['animations'])
        old,_=sample(dict(a,animations={'setup':{}}),'setup',0)
        new,_=sample(dict(b,animations={'setup':{}}),'setup',0)
        for p,q in zip(old['skirt'],new['skirt']):
            for x,y in zip(p,q):self.assertAlmostEqual(x,y,places=6)
        self.assertNotEqual(sample(a,'idle',1)[0]['skirt'],sample(b,'idle',1)[0]['skirt'])
        for f,g in zip(read(files)['animations']['idle'],read(out)['animations']['idle']):self.assertEqual(f['vertices']['shirt'],g['vertices']['shirt'])
        for name in ('images/skirt.png','images/shirt.png','skeleton.atlas'):self.assertEqual(files[name],out[name])
        self.assertEqual(json.loads(out['character-manifest.json'])['layers'][0]['state'],'weighted_candidate')

    def test_agent_review_preserves_origin_without_changing_geometry_or_authority(self):
        from jsonschema import Draft202012Validator
        from autospine_workbench.automation.character_region_mounts import valid_decision
        files, decision = self.source()
        human, _ = generate(files, decision)
        decision['decision_source'] = 'agent_review'
        out, report = generate(files, decision)
        saved = json.loads(out['region-mount-decision.json'])
        self.assertEqual(saved['decision_source'], 'agent_review')
        self.assertEqual(out['skeleton.json'], human['skeleton.json'])
        self.assertEqual(out['numeric-reference.json'], human['numeric-reference.json'])
        self.assertEqual(report['authority'], 'none')
        self.assertFalse(report['production_authorized'])
        schema = json.loads((Path(__file__).resolve().parents[1]/'schemas/region-mount-decision-v1.schema.json').read_bytes())
        Draft202012Validator(schema).validate(saved)
        for source in ('policy_auto', 'accepted', 'unknown'):
            self.assertFalse(valid_decision(dict(decision, decision_source=source)))

    def test_wrong_source_parent_or_bound_region_rejected(self):
        files,d=self.source()
        for change in ({'source_bundle_sha256':'f'*64},{'parents':{'skirt':'absent'}},{'parents':{'shirt':'chest'}}):
            with self.assertRaises(ValueError):generate(files,dict(d,**change))

    def test_batch_regions_keep_unselected_residual_pending(self):
        files,d=self.source();manifest=json.loads(files['character-manifest.json'])
        # Two existing regions belong to one source layer; only the reviewed one changes.
        manifest['layers'][0]['regions'].append({'region_id':'shirt','state':'static_reference'})
        manifest['layers']=manifest['layers'][:1]
        files['character-manifest.json']=canonical_bytes(manifest)
        d['source_bundle_sha256']=canonical_sha256({n:sha256(b).hexdigest() for n,b in files.items()})
        partial,_=generate(files,d)
        self.assertEqual(json.loads(partial['character-manifest.json'])['layers'][0]['state'],'partial')
        d['parents']['shirt']='pelvis';complete,_=generate(files,d)
        self.assertEqual(json.loads(complete['character-manifest.json'])['layers'][0]['state'],'weighted_candidate')
        self.assertEqual(json.loads(complete['skeleton.json'])['slots'],json.loads(files['skeleton.json'])['slots'])

    def test_durable_cas_revoke_exact_rebuild_and_schema(self):
        files,d=self.source()
        with TemporaryDirectory() as folder:
            m=SimpleNamespace(root=Path(folder),_lock=RLock(),projects=SimpleNamespace(get_project=lambda _:None),
                get=lambda *_:dict(status='needs_review',artifact_sha256=d['source_bundle_sha256']),verified_files=lambda *_:files,
                application=SimpleNamespace(store=SimpleNamespace(read=lambda _:files,publish=lambda _: 'b'*64)))
            body=dict(action='replace',expected_head_sha256=None,job_id='job',decision=d)
            saved=save(m,'project',body);self.assertEqual(saved,overview(m,'project'))
            from jsonschema import Draft202012Validator
            root=Path(__file__).parents[1]/'schemas'
            schema=json.loads((root/'character-region-mounts-v1.schema.json').read_bytes())
            schema['properties']['decision']['oneOf'][1]=json.loads((root/'region-mount-decision-v1.schema.json').read_bytes())
            Draft202012Validator(schema).validate(saved['review'])
            with self.assertRaisesRegex(RuntimeError,'conflict'):save(m,'project',body)
            request=dict(project_id='project',region_mounts_sha256=saved['head_sha256'])
            with patch('autospine_workbench.automation.character_residual_defaults.apply',side_effect=lambda m,q,r:r):
                self.assertEqual(apply_saved(m,request,dict(artifact_sha256=d['source_bundle_sha256']))['artifact_sha256'],'b'*64)
                with self.assertRaisesRegex(RuntimeError,'source_changed'):apply_saved(m,request,dict(artifact_sha256='c'*64))
            original=(m.root/'region-mount-decisions/project/000000.json').read_bytes()
            revoked=save(m,'project',dict(action='revoke',expected_head_sha256=saved['head_sha256']))
            self.assertFalse(revoked['active']);self.assertEqual(original,(m.root/'region-mount-decisions/project/000000.json').read_bytes())
