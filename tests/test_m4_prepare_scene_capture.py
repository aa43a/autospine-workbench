import unittest
from m4_prepare_scene_capture import select_frames


class CaptureFramesTests(unittest.TestCase):
    def test_switch_before_exact_after_are_kept(self):
        frames=[dict(time=i/1000) for i in range(1001)]
        picked=select_frames(frames,dict(slots={'leg':dict(attachment=[dict(time=.5,name='pose')])}),[])
        times={f['time'] for f in picked}
        self.assertTrue({0,.499,.5,.501,1}<=times)

    def test_missing_switch_reference_rejected(self):
        with self.assertRaisesRegex(ValueError,'boundary_missing'):
            select_frames([dict(time=0),dict(time=1)],dict(drawOrder=[dict(time=.5)]),[])
