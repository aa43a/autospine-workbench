from copy import deepcopy
from hashlib import sha256
import unittest
from PIL import Image
from autospine_workbench.asset.planning.residual_locations import locate, clusters
from autospine_workbench.asset.planning.wing_edge_ownership import encode
from autospine_workbench.benchmark.residual_location_cli import build


def fixture():
    camera = dict(width=4, height=4, world_center=[2, 2], world_size=[4, 4])
    row = dict(id='layer-001', tick=0, targets=[dict(pixel=[1, 1], delta=10, exposed=True)],
               world_vertices=[0, 0, 4, 0, 4, 4, 0, 4], uvs=[0, 1, 1, 1, 1, 0, 0, 0], triangles=[0, 1, 2, 0, 2, 3])
    return row, camera


class ResidualLocationTests(unittest.TestCase):
    def test_pixel_center_uv_and_bilinear_neighborhood(self):
        row, camera = fixture(); result = locate(row, camera, [4, 4])[0]
        self.assertEqual(result['world_xy'], [1.5, 1.5])
        self.assertEqual(result['mapping']['texture_sample_xy'], [1, 2])
        self.assertEqual(result['mapping']['texel_neighborhood'], [[1, 2], [1, 3], [2, 2], [2, 3]])

    def test_rotated_quad_and_unmapped_samples_preserved(self):
        row, camera = fixture(); row['world_vertices'] = [4, 0, 4, 4, 0, 4, 0, 0]
        self.assertEqual(locate(row, camera, [4, 4])[0]['mapping']['texture_sample_xy'], [1, 1])
        row['world_vertices'] = [10, 10, 14, 10, 14, 14, 10, 14]
        result = locate(row, camera, [4, 4]); self.assertEqual(len(result), 1); self.assertIsNone(result[0]['mapping'])

    def test_invalid_geometry_and_pixels_rejected(self):
        for mode in ['index', 'nan', 'pixel']:
            row, camera = fixture()
            if mode == 'index': row['triangles'][0] = -1
            if mode == 'nan': row['world_vertices'][0] = float('nan')
            if mode == 'pixel': row['targets'][0]['pixel'] = [5, 0]
            with self.subTest(mode=mode), self.assertRaises(ValueError): locate(row, camera, [4, 4])

    def test_display_grouping_preserves_every_sample(self):
        points = [dict(pixel=p) for p in [[0, 0], [4, 4], [8, 8], [20, 20]]]
        self.assertEqual(clusters(points), [[0, 1, 2], [3]])

    def test_exact_local_report_and_source_images_unchanged(self):
        row, camera = fixture()
        row.update(source_image='source.png', full_image='full.png', without_image='without.png', setup_vertices_xy=[[10, 20]])
        raw = encode(Image.new('RGBA', (4, 4), (100, 150, 200, 128)))
        files = {name: raw for name in ['source.png', 'full.png', 'without.png']}
        capture = dict(schema='autospine.residual-location-capture/v1', source_preview_sha256='a'*64, authority='none',
                       production_authorized=False, camera=camera, rows=[row], files={n: sha256(v).hexdigest() for n,v in files.items()})
        before = deepcopy((capture, files)); report, output = build(capture, files)
        self.assertEqual((capture, files), before)
        self.assertEqual((report['target_count'], report['mapped_count'], report['cluster_count']), (1, 1, 1))
        self.assertEqual(build(capture, files), (report, output))
        for name, digest in report['files'].items(): self.assertEqual(sha256(output[name]).hexdigest(), digest)
        files['source.png'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'file_changed'): build(capture, files)
