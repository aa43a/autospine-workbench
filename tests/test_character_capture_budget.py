import unittest
from autospine_workbench.automation.character_capture import runtime_timeout


class CaptureBudgetTests(unittest.TestCase):
    def test_scales_with_frames_and_remains_bounded(self):
        self.assertEqual(runtime_timeout(129),180)
        self.assertEqual(runtime_timeout(2062),473)
        self.assertGreater(runtime_timeout(2062),runtime_timeout(1675))
        self.assertEqual(runtime_timeout(1000000),900)

    def test_invalid_counts_rejected(self):
        for count in (True,0,-1,1.5):
            with self.assertRaisesRegex(ValueError,'frame_count'):
                runtime_timeout(count)
