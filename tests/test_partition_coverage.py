"""Full alpha coverage is independent from speculative distal weight changes."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import unittest
from PIL import Image
from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.partition_pixels import png
from autospine_workbench.asset.joints.partition_mesh_coverage import improve
from autospine_workbench.resolved_project import canonical_sha256


def inputs(single=False):
    raw,source,side,bones,skeleton=fixture()
    image=Image.open(BytesIO(raw));image.putpixel((23,79),(90,80,70,1))
    raw=png('RGBA',image.size,image.tobytes())
    row=build_region(raw,source,side,['foot_l'] if single else bones,skeleton)
    baseline={'schema':'autospine.partition-mesh/v1','profile':'partition-joint-plane-grid-v1','authority':'none',
              'production_authorized':False,'source_skeleton_sha256':canonical_sha256(skeleton),
              'source_partitions_sha256':'1'*64,'residual_policy':'retain_original','residuals':[],
              'seam_status':'not_evaluated','runtime_status':'not_evaluated','layers':[row]}
    return baseline,{'layers':[{**source,'layer_id':row['layer_id']}]},skeleton,{row['layer_id']:raw}


class PartitionCoverageTests(unittest.TestCase):
    def test_low_alpha_pixel_included_old_baseline_unchanged(self):
        args=inputs(True);before=deepcopy(args)
        self.assertGreater(args[0]['layers'][0]['raster_qa']['uncovered_alpha_pixels'],0)
        doc=improve(*args);row=doc['layers'][0]
        self.assertEqual(row['raster_qa']['uncovered_alpha_pixels'],0)
        self.assertTrue(row['qa']['passed'])
        self.assertEqual(row['status'],'candidate_requires_review')
        self.assertEqual(args,before)
        self.assertEqual(doc,improve(*args))

    def test_distal_trials_separate_and_reconstruct(self):
        args=inputs();doc=improve(*args)
        trial=doc['distal_trials'][0]
        self.assertFalse(trial['adopted'])
        self.assertLess(trial['qa']['setup_max_error'],1e-7)
        self.assertLess(trial['qa']['weight_sum_max_error'],1e-9)
        self.assertEqual(len(trial['qa']['probes']),len(doc['layers'][0]['qa']['probes']))
        self.assertNotEqual(trial['weights'],doc['layers'][0]['weights'])
        self.assertTrue(all(i['weight']>=0 for w in trial['weights'] for i in w))
        args[-1][next(iter(args[-1]))]+=b'x'
        with self.assertRaisesRegex(ValueError,'image_changed'):improve(*args)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:self.skipTest('jsonschema unavailable')
        path=Path(__file__).resolve().parents[1]/'schemas/partition-mesh-full-alpha-v2.schema.json'
        Draft202012Validator(json.loads(path.read_text('utf-8'))).validate(improve(*inputs()))
        Draft202012Validator(json.loads(path.read_text('utf-8'))).validate(improve(*inputs(),supported=True))

    def test_faint_secondary_component_does_not_change_perceptible_gate(self):
        from autospine_workbench.asset.joints.full_alpha_grid import build_supported_grid
        from autospine_workbench.alpha_grid_mesh import build_alpha_grid_mesh,AlphaGridMeshError
        from autospine_workbench.png_rgba import decode_rgba_png
        from autospine_workbench.asset.joints.partition_mesh_qa import raster_support
        raw,_,_,_,_=fixture();image=Image.open(BytesIO(raw))
        for x in range(20,23):
            for y in range(60,66):image.putpixel((x,y),(50,60,70,1))
        source=decode_rgba_png(png('RGBA',image.size,image.tobytes()))
        with self.assertRaises(AlphaGridMeshError):build_alpha_grid_mesh(source,grid_step_px=4,alpha_threshold=1)
        grid=build_supported_grid(source,4)
        self.assertEqual(raster_support(source.pixels[3::4],source.width,source.height,
                         grid.vertices_xy,grid.triangles,(0,0))['uncovered_alpha_pixels'],0)
