from types import SimpleNamespace
from unittest.mock import patch
import unittest
from autospine_workbench.targets.character43.camera_ankle_targets import extract
from autospine_workbench.targets.character43.source_ankle_targets import targets


class CameraAnkleTests(unittest.TestCase):
    def observe(self,shift=(0,0,0),moving=0):
        times=[0,.25,.5,.75,1]
        roots=[shift]*5
        points=[[[shift[0]+x+moving*t,shift[1]+10,shift[2]+2] for x in (-3,3)] for t in times]
        source=dict(times=times,points=points,source_reference_length=10)
        bundle=SimpleNamespace(bundle_sha256='a'*64,clip_sha256='b'*64,
            motion=dict(duration_ticks=1000000,ticks_per_second=1000000))
        with patch('autospine_workbench.targets.character43.camera_ankle_targets.source_ankles',return_value=source), \
             patch('autospine_workbench.targets.character43.camera_ankle_targets.source_vectors',return_value=({},roots,10)):
            return extract(bundle,[dict(time=0,yaw=0),dict(time=1,yaw=360)])

    def test_stationary_3d_feet_move_on_screen_with_camera(self):
        value=self.observe();rows=targets(value,[[-30,-100],[30,-100]],100)
        self.assertEqual(rows[0]['targets'],[[-30,-100],[30,-100]])
        for actual,expected in zip(rows[2]['targets'],[[30,-100],[-30,-100]]):
            for a,b in zip(actual,expected):self.assertAlmostEqual(a,b)
        self.assertEqual(value['frozen_camera_points'][0],value['frozen_camera_points'][2])
        self.assertNotEqual(value['camera_displacement'][0],value['camera_displacement'][2])

    def test_scene_translation_invariant_and_source_motion_preserved(self):
        base=self.observe(moving=2);shifted=self.observe((123,-456,789),moving=2)
        self.assertEqual(base,shifted)
        self.assertAlmostEqual(base['frozen_camera_points'][-1][0][0]-base['frozen_camera_points'][0][0][0],2)
        self.assertAlmostEqual(base['points'][-1][0][0]-base['points'][0][0][0],2)
