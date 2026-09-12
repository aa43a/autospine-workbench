from io import BytesIO
import json
import unittest
from PIL import Image
from autospine_workbench.targets.character43.static_region_review import build


def fixture():
    image = Image.new('RGBA', (4, 3)); image.putpixel((2, 1), (255, 255, 255, 255))
    image.putpixel((1, 1), (255, 0, 0, 3)); raw = BytesIO(); image.save(raw, format='PNG')
    manifest = {'layers': [{'layer_id': 'source', 'name': '<source>', 'regions': [
        {'region_id': 'part', 'state': 'static_reference'}]}]}
    skeleton = {'skins': [{'attachments': {'part': {'part': {'path': 'texture'}}}}]}
    return {'character-manifest.json': json.dumps(manifest).encode(),
            'skeleton.json': json.dumps(skeleton).encode(), 'images/texture.png': raw.getvalue()}


class StaticRegionTests(unittest.TestCase):
    def test_exact_ownership_alpha_and_crop_preserve_original(self):
        files = fixture(); before = dict(files); outputs, links = build(files)
        self.assertEqual(files, before)
        report = json.loads(outputs['static-regions/report.json']); row = report['rows'][0]
        self.assertEqual(row['visible_pixels'], 2)
        self.assertEqual(row['alpha_at_least_8_pixels'], 1)
        self.assertEqual(row['crop_bbox'], [1, 1, 3, 2])
        self.assertEqual(row['layer_id'], 'source')
        self.assertEqual(links, {'source': ['static-regions/index.html#region-0']})
        self.assertIn(b'&lt;source&gt;', outputs['static-regions/index.html'])
        self.assertFalse(report['production_authorized'])
        self.assertEqual(build(files), (outputs, links))

    def test_unsafe_image_path_rejected(self):
        files = fixture(); doc = json.loads(files['skeleton.json'])
        doc['skins'][0]['attachments']['part']['part']['path'] = '../secret'
        files['skeleton.json'] = json.dumps(doc).encode()
        with self.assertRaisesRegex(ValueError, 'path'):
            build(files)

    def test_duplicate_owner_rejected(self):
        files = fixture(); doc = json.loads(files['character-manifest.json'])
        doc['layers'].append(doc['layers'][0]); files['character-manifest.json'] = json.dumps(doc).encode()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build(files)
