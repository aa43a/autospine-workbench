from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from autospine_workbench.targets.character43.framebuffer_equivalence import compare


def fixture(root, color=(1, 2, 3, 255)):
    root.mkdir()
    out = BytesIO(); Image.new('RGBA', (2, 2), color).save(out, format='PNG')
    raw = out.getvalue(); (root/'frame.png').write_bytes(raw)
    report = dict(schema='autospine.character-framebuffer/v1', passed=True, authority='none',
                  production_authorized=False, bundle_sha256='a'*64,
                  info=dict(width=2, height=2, left=0, bottom=0, slots=1),
                  results=[dict(animation='test', index=0, time=0)],
                  screenshots=[dict(animation='test', index=0, file='frame.png', sha256=sha256(raw).hexdigest())])
    for key in ['runtime_package', 'runtime_version', 'runtime_sha256', 'harness_sha256', 'tool_sha256',
                'draw_order_reader_sha256', 'reference_reader_sha256', 'browser_sha256', 'profile']:
        report[key] = 'same'
    (root/'report.json').write_text(json.dumps(report))
    return report


class FramebufferEquivalenceTests(unittest.TestCase):
    def test_equal_and_changed_alpha_with_different_slot_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fixture(root/'a'); report = fixture(root/'b')
            report['info']['slots'] = 3
            (root/'b/report.json').write_text(json.dumps(report))
            result = compare(root/'a', root/'b')
            self.assertTrue(result['passed']); self.assertFalse(result['selected'])
            fixture(root/'c', (1, 2, 3, 254))
            result = compare(root/'a', root/'c')
            self.assertFalse(result['passed'])
            self.assertEqual(result['frames'][0]['changed_pixels'], 4)
            self.assertEqual(result['frames'][0]['max_channel_delta'], 1)

    def test_partial_stale_camera_and_environment_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); fixture(root/'a'); original = fixture(root/'b')
            for field, value, reason in [('screenshots', [], 'incomplete_frame'),
                                         ('browser_sha256', 'changed', 'environment_mismatch'),
                                         ('info', dict(width=2,height=2,left=1,bottom=0,slots=1), 'camera_or_frames')]:
                report = dict(original); report[field] = value
                (root/'b/report.json').write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, reason):
                    compare(root/'a', root/'b')
            (root/'b/report.json').write_text(json.dumps(original))
            (root/'b/frame.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'image_identity'):
                compare(root/'a', root/'b')


if __name__ == '__main__':
    unittest.main()
