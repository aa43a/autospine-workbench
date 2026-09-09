from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import unittest
import json
from pathlib import Path
from PIL import Image
from autospine_workbench.asset.planning.component_partitions import build, validate


def fixture():
    im = Image.new('RGBA', (4, 3)); im.putdata([(20, 30, 40, a) for a in [255, 0, 255, 0, 255, 7, 0, 255, 0, 0, 0, 0]])
    stream = BytesIO(); im.save(stream, format='PNG'); raw = stream.getvalue()
    return dict(layer_id='layer-001', bbox=[10, 20, 14, 23], image_sha256=sha256(raw).hexdigest()), raw


class ComponentPartitionTests(unittest.TestCase):
    def test_four_connectivity_residual_and_exact_disjoint_visible_coverage(self):
        layer, raw = fixture(); value = build(layer, raw)
        self.assertEqual(len(value['components']), 3)
        self.assertEqual(value['components'][0]['bbox'], [10, 20, 11, 22])
        self.assertEqual(value['residual']['pixel_count'], 1)
        pixels = []
        for row in value['components'] + [value['residual']]:
            pixels.extend((x, y) for y, start, end in row['runs'] for x in range(start, end))
            self.assertIsNone(row['owner']); self.assertEqual(row['bone_ids'], [])
        self.assertEqual(len(pixels), len(set(pixels)))
        self.assertEqual(set(pixels), {(0,0),(2,0),(0,1),(1,1),(3,1)})
        self.assertEqual(validate(layer, raw, value), build(layer, raw))
        import jsonschema
        jsonschema.validate(value, json.loads(Path('schemas/component-partition-candidate-v1.schema.json').read_text()))

    def test_source_and_ownership_tampering_fail(self):
        layer, raw = fixture(); value = build(layer, raw)
        with self.assertRaises(ValueError): build(layer, raw+b'changed')
        changed = deepcopy(value); changed['components'][0]['owner'] = 'left'
        with self.assertRaises(ValueError): validate(layer, raw, changed)
        changed = deepcopy(value); changed['residual']['runs'] = []
        with self.assertRaises(ValueError): validate(layer, raw, changed)

    def test_empty_layer_is_blocked(self):
        im = Image.new('RGBA', (1,1)); stream = BytesIO(); im.save(stream, format='PNG'); raw = stream.getvalue()
        value = build(dict(layer_id='empty', bbox=[0,0,1,1], image_sha256=sha256(raw).hexdigest()), raw)
        self.assertEqual(value['status'], 'blocked'); self.assertEqual(value['visible_pixel_count'], 0)
