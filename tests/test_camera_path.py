import math
import unittest
from copy import deepcopy

from autospine_workbench.targets.character43.camera_path import plan


TORSO=[(-1,-2,0),(1,-2,0),(0,0,0)]
ROLE='humanoid.arm.lower.right'


class CameraPathTests(unittest.TestCase):
    def test_shared_camera_avoids_shortening_with_bounded_speed(self):
        times=[0,.5,1]
        vectors={ROLE:[(math.cos(a),0,math.sin(a)) for a in (0,math.pi/4,math.pi/2)]}
        before=deepcopy(vectors)
        result=plan(vectors,[TORSO]*3,times)
        self.assertEqual(result['status'],'sampled_path_found')
        self.assertEqual(result['records'][0]['yaw_degrees'],0)
        self.assertLess(result['records'][-1]['yaw_degrees'],-20)
        self.assertLessEqual(result['maximum_speed_deg_per_second'],60)
        self.assertTrue(all(r['passed'] for r in result['records']))
        self.assertEqual(vectors,before)
        self.assertFalse(result['selected'])

    def test_visible_frames_do_not_imply_a_continuous_path(self):
        result=plan({ROLE:[(1,0,0),(0,0,1)]},[TORSO]*2,[0,1/30])
        self.assertEqual(result['status'],'no_continuous_qualified_path')
        failure=result['failure']
        self.assertTrue(failure['qualified_angles'])
        self.assertEqual(failure['frame'],1)
        self.assertGreater(failure['minimum_required_speed_deg_per_second'],60)
        self.assertEqual(result['records'],[])

    def test_invalid_or_unobservable_data_is_not_adopted(self):
        for times in ([0,0],[0,float('nan')]):
            with self.assertRaises(ValueError):plan({ROLE:[(1,0,0)]*2},[TORSO]*2,times)
        with self.assertRaisesRegex(ValueError,'initial_limb'):
            plan({ROLE:[(0,0,1)]*2},[TORSO]*2,[0,1])
        with self.assertRaisesRegex(ValueError,'options'):
            plan({ROLE:[(1,0,0)]*2},[TORSO]*2,[0,1],maximum_speed=1000)


if __name__=='__main__':unittest.main()
