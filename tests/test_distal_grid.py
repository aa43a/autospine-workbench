"""Density adds conforming support without changing source or corrective limits."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.test_partition_mesh import fixture
from autospine_workbench.asset.joints.partition_mesh import build_region
from autospine_workbench.asset.joints.distal_grid import build_grid, refined_edges, refine
from autospine_workbench.asset.joints.distal_corrective import prepare, sample, ANGLES
from autospine_workbench.asset.joints.partition_mesh_qa import raster_support
from autospine_workbench.png_rgba import decode_rgba_png
from autospine_workbench.resolved_project import canonical_sha256


class DistalGridTests(unittest.TestCase):
    def inputs(self):
        raw, source, side, ids, skeleton = fixture()
        row = build_region(raw, source, side, ids, skeleton)
        mesh = {'profile':'partition-full-alpha-supported-v2',
                'source_skeleton_sha256':canonical_sha256(skeleton), 'layers':[row]}
        candidate = {'layers':[dict(source, layer_id=row['layer_id'])]}
        return mesh, candidate, skeleton, {row['layer_id']:raw}

    def test_conforming_grid_full_alpha_and_determinism(self):
        image = decode_rgba_png(fixture()[0])
        # Tiny positive-alpha island must not be silently omitted.
        pixels = bytearray(image.pixels); pixels[3] = 1
        image = type(image)(image.width, image.height, bytes(pixels))
        grid = build_grid(image, 8, (12, 60), 9)
        self.assertEqual(grid, build_grid(image, 8, (12, 60), 9))
        coverage = raster_support(image.pixels[3::4], image.width, image.height,
                                  grid.vertices_xy, grid.triangles, (0,0))
        self.assertEqual(coverage['uncovered_alpha_pixels'], 0)
        # No unused vertex can lie strictly inside a triangle edge (T junction).
        for tri in grid.triangles:
            for ia, ib in zip(tri, tri[1:]+tri[:1]):
                a, b = grid.vertices_xy[ia], grid.vertices_xy[ib]
                for j, p in enumerate(grid.vertices_xy):
                    if j in (ia, ib): continue
                    cross = (p[0]-a[0])*(b[1]-a[1])-(p[1]-a[1])*(b[0]-a[0])
                    dot = sum((p[k]-a[k])*(p[k]-b[k]) for k in (0,1))
                    self.assertFalse(cross == 0 and dot < 0)

    def test_setup_purity_and_same_correction_budget(self):
        args = self.inputs(); before = deepcopy(args)
        result = refine(*args); row = result['layers'][0]
        self.assertEqual(args, before)
        self.assertEqual(result, refine(*args))
        self.assertLess(row['qa']['setup_max_error'], 1e-7)
        self.assertEqual(row['raster_qa']['uncovered_alpha_pixels'], 0)
        old = prepare(args[0]['layers'][0], args[2]['bones'])
        new = prepare(row, args[2]['bones'])
        self.assertEqual(new['budget'], old['budget'])
        self.assertGreater(sum(new['free']), sum(old['free']))
        for angle in ANGLES:
            qa = sample(new, angle)['qa']
            self.assertLessEqual(qa['projection_displacement_px'], old['budget']+1e-7)
            self.assertLess(qa['fixed_vertex_error'], 1e-7)
            self.assertLess(qa['offset_reconstruction_error'], 1e-7)

    def test_invalid_sources_and_limits_fail_closed(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): refined_edges(80, 8, 40, value)
        args = self.inputs(); args[0]['source_skeleton_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'source_mismatch'): refine(*args)
        args = self.inputs(); args[-1][next(iter(args[-1]))] = b'changed'
        with self.assertRaisesRegex(ValueError, 'image_mismatch'): refine(*args)
        image = decode_rgba_png(fixture()[0])
        with patch('autospine_workbench.alpha_grid_mesh.MAX_ATTACHMENT_VERTICES', 4):
            with self.assertRaises(ValueError): build_grid(image, 8, (12,60), 9)

    def test_exact_reader_rejects_changed_result(self):
        from autospine_workbench.benchmark.distal_grid_cli import read_experiment
        doc = {'schema':'autospine.distal-grid-experiment/v1', 'source_mesh_sha256':'a'*64, 'selected_method':None}
        changed = dict(doc, selected_method='adopted')
        with patch('autospine_workbench.benchmark.distal_grid_cli.read_mesh_report', return_value=changed), \
             patch('autospine_workbench.benchmark.distal_grid_cli.compile_report', return_value=(doc, None)):
            with self.assertRaisesRegex(ValueError, 'replay_mismatch'):
                read_experiment(None, {'dataset_id':'test'}, 'b'*64, workspace=None)
