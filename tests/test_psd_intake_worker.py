"""Real tiny PSD roundtrip and intake failure boundaries."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.automation.psd_intake_worker import (
    PsdIntakeError, extract_psd, inspect_header,
)


class PsdHeaderTests(unittest.TestCase):
    def test_bad_signature_and_canvas_rejected_before_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bad.psd'
            for signature, width, code in ((b'FAKE', 10, 'invalid_psd_header'),
                                            (b'8BPS', 9000, 'psd_canvas_limit')):
                source.write_bytes(struct.pack('>4sH6sHIIHH', signature, 1, bytes(6), 4, 10, width, 8, 3))
                with self.assertRaises(PsdIntakeError) as raised:
                    inspect_header(source)
                self.assertEqual(raised.exception.reason_code, code)


@unittest.skipUnless(importlib.util.find_spec('psd_tools') and importlib.util.find_spec('PIL'),
                     'optional PSD decoder unavailable')
class PsdExtractionTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'example.psd'
        psd = PSDImage.new('RGBA', (24, 20))
        PixelLayer.frompil(Image.new('RGBA', (4, 6), (255, 10, 20, 255)),
                           psd, name='arm/right', left=7, top=8)
        PixelLayer.frompil(Image.new('RGBA', (3, 2), (10, 255, 20, 255)),
                           psd, name='head', left=10, top=2)
        psd.save(self.source)

    def test_real_roundtrip_offsets_order_alpha_and_portable_paths(self):
        from PIL import Image
        output = self.root / 'staging'
        result = extract_psd(self.source, output)
        self.assertEqual(result['canvas'], [24, 20])
        self.assertEqual(result['pixel_layers'], 2)
        self.assertEqual([r['name'] for r in result['layers']], ['arm/right', 'head'])
        arm = result['layers'][0]
        self.assertEqual(arm['bbox'], [7, 8, 11, 14])
        self.assertEqual(arm['component_areas_top5'], [24])
        output.rename(self.root / 'promoted')
        with Image.open(self.root / 'promoted' / arm['crop_path']) as image:
            self.assertEqual(image.size, (4, 6))
            self.assertEqual(image.getpixel((0, 0)), (255, 10, 20, 255))
        self.assertEqual(json.loads((self.root / 'promoted/audit.json').read_text())['sha256'], result['sha256'])

    def test_existing_staging_is_never_overwritten(self):
        output = self.root / 'staging'
        output.mkdir()
        with self.assertRaises(PsdIntakeError) as raised:
            extract_psd(self.source, output)
        self.assertEqual(raised.exception.reason_code, 'psd_staging_exists')

    def test_layer_budget_failure_never_writes_audit(self):
        output = self.root / 'staging'
        with patch('autospine_workbench.automation.psd_intake_worker.MAX_LAYERS', 1):
            with self.assertRaises(PsdIntakeError) as raised:
                extract_psd(self.source, output)
        self.assertEqual(raised.exception.reason_code, 'psd_layer_limit')
        self.assertFalse((output / 'audit.json').exists())

    def test_alpha_components_are_four_connected(self):
        from PIL import Image
        from autospine_workbench.automation.psd_intake_alpha import alpha_statistics
        image = Image.new('RGBA', (2, 2))
        image.putpixel((0, 0), (255, 0, 0, 255))
        image.putpixel((1, 1), (255, 0, 0, 8))
        stats = alpha_statistics(image)
        self.assertEqual(stats['component_areas_top5'], [1, 1])
        self.assertEqual(stats['alpha_opaque'], 1)


if __name__ == '__main__':
    unittest.main()
