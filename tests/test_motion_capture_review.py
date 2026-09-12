import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

frames = runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/review-motion-capture.py'))['frames']


class CaptureReviewTests(unittest.TestCase):
    def fixture(self, root):
        (root/'frames').mkdir()
        rows = []
        for i in (0, 8):
            raw = bytes([i]); name = f'frames/walk-{i}.png'
            (root/name).write_bytes(raw)
            rows.append(dict(animation='walk', index=i, file=name, sha256=hashlib.sha256(raw).hexdigest()))
        doc = dict(passed=True, runtime_package='@esotericsoftware/spine-webgl', screenshots=rows,
                   results=[dict(animation='walk', index=i, time=i/8) for i in (0, 8)])
        (root/'report.json').write_text(json.dumps(doc))
        return doc

    def test_replays_capture_times_not_invented_frame_rate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixture(root)
            self.assertEqual([r['time'] for r in frames(root)], [0, 1])

    def test_changed_image_and_failed_capture_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); doc = self.fixture(root)
            (root/'frames/walk-0.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'image_changed'): frames(root)
            doc['passed'] = False
            (root/'report.json').write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'official_capture'): frames(root)
