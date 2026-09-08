"""Alpha-conditioned widths retain upstream influence and source geometry."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.distal_width import measure,reweight
from autospine_workbench.asset.joints.distal_corrective import prepare,sample,ANGLES
from autospine_workbench.png_rgba import decode_rgba_png


class DistalWidthTests(unittest.TestCase):
    def test_measure_empty_slab_and_invalid_factor(self):
        args=fixture();image=decode_rgba_png(args[0]);bones=args[-1]['bones']
        evidence=measure(image,args[1]['bbox'][:2],bones)
        self.assertGreater(evidence['alpha_samples'],0)
        self.assertGreater(evidence['transverse_radius_px'],0)
        with self.assertRaisesRegex(ValueError,'unobservable'):measure(image,(10000,10000),bones)
        row=build_region(*args)
        for factor in (0,3,True,float('nan')):
            with self.assertRaises(ValueError):reweight(row,bones,evidence,factor)

    def test_preserve_geometry_upstream_and_setup(self):
        args=fixture();row=build_region(*args);before=deepcopy(row);bones=args[-1]['bones']
        evidence=measure(decode_rgba_png(args[0]),args[1]['bbox'][:2],bones)
        for factor in (1,2,4):
            result,policy=reweight(row,bones,evidence,factor)
            self.assertEqual((result,policy),reweight(row,bones,evidence,factor))
            self.assertEqual(result['vertices_xy'],row['vertices_xy'])
            self.assertEqual(result['triangles'],row['triangles'])
            for a,b in zip(result['weights'],row['weights']):
                self.assertEqual(a[0],b[0])
                self.assertAlmostEqual(sum(i['weight'] for i in a),1)
                self.assertEqual([i['local_xy'] for i in a],[i['local_xy'] for i in b])
            context=prepare(result,bones)
            self.assertEqual(context['budget'],prepare(row,bones)['budget'])
            for angle in ANGLES:
                qa=sample(context,angle)['qa']
                self.assertLess(qa['offset_reconstruction_error'],1e-7)
                self.assertLessEqual(qa['projection_displacement_px'],context['budget']+1e-7)
            self.assertEqual(sample(context,0)['positions'],row['vertices_xy'])
        self.assertEqual(row,before)

    def test_width_cap_and_invalid_evidence(self):
        args=fixture();row=build_region(*args);bones=args[-1]['bones']
        _,policy=reweight(row,bones,{'transverse_radius_px':10000},4)
        self.assertTrue(policy['capped'])
        self.assertEqual(policy['halfwidth_px'],policy['cap_px'])
        for bad in (-1,float('inf'),float('nan')):
            with self.assertRaises(ValueError):reweight(row,bones,{'transverse_radius_px':bad},2)

    def test_reader_rejects_tampered_result(self):
        from autospine_workbench.benchmark.distal_width_cli import read_experiment
        doc={'source_mesh_sha256':'a'*64,'selected_method':None}
        with patch('autospine_workbench.benchmark.distal_width_cli.read_mesh_report',return_value=dict(doc,selected_method=2)), \
             patch('autospine_workbench.benchmark.distal_width_cli.compile_report',return_value=(doc,None)):
            with self.assertRaisesRegex(ValueError,'replay_mismatch'):
                read_experiment(None,{'dataset_id':'test'},'b'*64,workspace=None)
