import math
import unittest
from autospine_workbench.targets.character43.source_foot_orientation import camera_rotation


class FootViewTests(unittest.TestCase):
    def test_zero_and_stationary_frame_remain_unchanged(self):
        identity=[[1,0,0],[0,1,0],[0,0,1]]
        self.assertEqual(camera_rotation(identity,0),identity)
        for yaw in (-45,45):
            for row,want in zip(camera_rotation(identity,yaw),identity):
                for a,b in zip(row,want):self.assertAlmostEqual(a,b)

    def test_side_camera_turns_world_pitch_into_screen_rotation(self):
        a=math.pi/6;c,s=math.cos(a),math.sin(a)
        pitch=[[1,0,0],[0,c,-s],[0,s,c]]
        for yaw,expected in ((90,30),(-90,-30)):
            m=camera_rotation(pitch,yaw)
            angle=math.degrees(math.atan2(m[1][0]-m[0][1],m[0][0]+m[1][1]))
            self.assertAlmostEqual(angle,expected)

    def test_invalid_yaw_rejected(self):
        for yaw in (True,91,float('nan')):
            with self.assertRaises(ValueError):camera_rotation([],yaw)
