"""Target fidelity uses dense influence offsets, including zero-weight entries."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator
from test_ordinary_sleeve import fixture
from autospine_workbench.asset.planning.ordinary_sleeve_repair import build as repair_build
from autospine_workbench.asset.planning.ordinary_sleeve_deform import build as deform_build
from autospine_workbench.asset.planning.ordinary_deform_interpolation import build as interpolation_build
from autospine_workbench.targets.spine43.ordinary_deform import build,validate
from autospine_workbench.targets.spine43.ordinary_deform_encoding import encode
from autospine_workbench.targets.spine43.ordinary_deform_checks import inspect
from autospine_workbench.benchmark.mesh_storage import publish_mesh_report,read_mesh_report
from autospine_workbench.resolved_project import canonical_sha256


def closure(residual=False):
    source,draft,skeleton=fixture();skeleton['canvas']=[64,64]
    skeleton['bones'].insert(0,dict(id='chest',parent_id=None,head_xy=[0.,0.],tail_xy=[0.,10.],
                                  length=10.,world_rotation_degrees=0.,setup_local=dict(x=0.,y=0.,rotation_degrees=0.)))
    for i,bone in enumerate(skeleton['bones'][1:]):
        bone.update(length=10.,setup_local=dict(x=0. if i==0 else 10.,y=0.,rotation_degrees=0.))
    source['skeleton_sha256']=canonical_sha256(skeleton)
    mesh=source['records'][0]['mesh'];mesh['uvs']=[[x/64,y/64] for x,y in mesh['vertices_xy']]
    source['records'][0]['isolated_image_sha256']='b'*64
    if residual:source['records'].append(dict(layer_id='residual',component_id='c2',mesh=None))
    repair=repair_build(source,draft,skeleton);deform=deform_build(repair,source,draft,skeleton)
    interpolation=interpolation_build(deform,repair=repair,source=source,draft=draft,skeleton=skeleton)
    return dict(interpolation=interpolation,deform=deform,repair=repair,source=source,draft=draft,skeleton=skeleton)


class OrdinaryDeformTargetTests(unittest.TestCase):
    def test_full_closure_four_tracks_schema_storage_and_residual(self):
        inputs=closure(True);report,documents=build(**inputs)
        self.assertEqual(report,validate(report,**inputs))
        self.assertEqual(report['records'][0]['status'],'target_sampled_passed')
        self.assertEqual(report['records'][1]['status'],'blocked')
        self.assertIsNone(report['records'][1]['qa']);self.assertIsNone(report['records'][1]['target_sha256'])
        self.assertEqual(len(documents),1)
        qa=report['records'][0]['qa'];self.assertEqual(len(qa['checks']),4)
        for check in qa['checks']:
            self.assertEqual(check['sample_count'],513);self.assertEqual(check['failed_samples'],[])
            self.assertLessEqual(check['key_error_px'],1e-7)
            self.assertLessEqual(check['between_key_error_px'],qa['between_key_tolerance_px'])
        schema=json.loads(Path('schemas/ordinary-deform-target-v1.schema.json').read_text())
        Draft202012Validator.check_schema(schema);Draft202012Validator(schema).validate(report)
        with tempfile.TemporaryDirectory() as root:
            sha=publish_mesh_report(root,'project-component-partitions',report)
            self.assertEqual(read_mesh_report(root,'project-component-partitions',sha),report)

    def test_nonzero_deform_encodes_all_influences_and_subframes(self):
        inputs=closure();row=deepcopy(inputs['deform']['records'][0]);mesh=inputs['source']['records'][0]['mesh']
        for track in row['tracks']:
            for key in track['keys']:
                delta=.02*math.sin(2*math.pi*key['tick']/128) if key['tick'] not in (0,64,128) else 0.
                key['offsets']=[dict(vertex_id=0,delta_xy=[delta,.5*delta])] if delta else []
        doc=encode(row,mesh,inputs['skeleton'],'c'*64);name='arm-c1'
        for animation in doc['animations'].values():
            keys=animation['attachments']['default'][name][name]['deform']
            self.assertEqual(len(keys),129)
            self.assertEqual(len(keys[32]['vertices']),len(row['weights'])*3*2)
            self.assertTrue(any(abs(v)>0 for v in keys[32]['vertices'][:2]))
            # Vertex zero's first influence has zero weight but its delta remains encoded.
            self.assertEqual(row['weights'][0][0]['weight'],0.)
        qa=inspect(doc,row,inputs['skeleton'])
        self.assertTrue(qa['passed'],qa)
        self.assertTrue(all(c['key_error_px']<1e-7 for c in qa['checks']))
        self.assertTrue(any(c['between_key_error_px']>0 for c in qa['checks']))
        corrupted=deepcopy(doc)
        corrupted['animations']['hand']['attachments']['default'][name][name]['deform'][32]['vertices'][2]+=2.
        broken=inspect(corrupted,row,inputs['skeleton'])
        self.assertFalse(broken['passed'])
        self.assertIn('target_key_reconstruction_failure',broken['checks'][1]['reason_codes'])
        for change in (lambda k:k['vertices'].append(0.), lambda k:k['vertices'].pop(),
                       lambda k:k['vertices'].__setitem__(0,float('nan'))):
            corrupted=deepcopy(doc)
            change(corrupted['animations']['hand']['attachments']['default'][name][name]['deform'][32])
            with self.assertRaises(ValueError):inspect(corrupted,row,inputs['skeleton'])

    def test_tampered_report_source_and_blocked_row_are_rejected(self):
        inputs=closure(True);report,_=build(**inputs)
        bad=deepcopy(report);bad['records'][1]['status']='target_sampled_passed'
        with self.assertRaises(ValueError):validate(bad,**inputs)
        bad=deepcopy(report);bad['source_sha256']='f'*64
        with self.assertRaises(ValueError):validate(bad,**inputs)
        changed=deepcopy(inputs);changed['source']['records'][0]['mesh']['uvs'][0]=[.9,.9]
        with self.assertRaises(ValueError):build(**changed)


if __name__=='__main__':unittest.main()
