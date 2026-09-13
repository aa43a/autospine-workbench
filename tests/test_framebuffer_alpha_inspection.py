"""Low-alpha white texels must not become opaque diagnostic speckles."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
import unittest

from PIL import Image

spec = spec_from_file_location('framebuffer_alpha_inspector',
    Path(__file__).resolve().parents[1] / 'tools/inspect-framebuffer-alpha.py')
module = module_from_spec(spec)
spec.loader.exec_module(module)


class FramebufferAlphaTests(unittest.TestCase):
    def test_compositing_preserves_low_alpha_contribution(self):
        image = Image.new('RGBA', (4, 1))
        image.putdata([(255, 255, 255, 1), (255, 255, 255, 7),
                       (50, 60, 70, 255), (255, 0, 0, 0)])
        stream = BytesIO(); image.save(stream, format='PNG'); raw = stream.getvalue()
        report, views = module.inspect(raw, sha256(raw).hexdigest())
        self.assertEqual(report['counts']['alpha_1_to_7'], 2)
        self.assertEqual(report['low_alpha_black_rgb_peak'], [7, 7, 7])
        self.assertEqual(views['black'].getpixel((0, 0)), (1, 1, 1))
        self.assertEqual(views['black'].getpixel((3, 0)), (0, 0, 0))
        self.assertEqual(views['white'].getpixel((3, 0)), (255, 255, 255))
        self.assertEqual(views['slate'].getpixel((2, 0)), (50, 60, 70))
        self.assertTrue(all(view.mode == 'RGB' for view in views.values()))
        self.assertFalse(report['production_authorized'])

    def test_rejects_wrong_capture(self):
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            module.inspect(b'not-the-reviewed-image', '0' * 64)
