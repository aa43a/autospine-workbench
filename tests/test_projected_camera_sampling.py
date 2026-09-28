import math
import unittest
from autospine_workbench.targets.character43.projected_camera_sampling import refine
from autospine_workbench.targets.character43.camera_sampling import schedule,interpolate
from autospine_workbench.targets.character43.camera_track import sample
from autospine_workbench.targets.character43.oblique_motion import project

class ProjectedSamplingTests(unittest.TestCase):
    def test_near_side_direction_is_refined_without_changing_native_samples(self):
        times=[0,.5,1];keys=[dict(time=0,yaw=0),dict(time=1,yaw=360)]
        vectors={'arm':[[1,.03,0]]*3}
        result=refine(times,vectors,keys,1,1)
        self.assertTrue(set(schedule(times,keys,1))<=set(result))
        angles=[math.degrees(math.atan2(.03,math.cos(math.radians(sample(keys,t))))) for t in result]
        self.assertLessEqual(max(abs((b-a+180)%360-180) for a,b in zip(angles,angles[1:])),12)
        self.assertGreater(len(result),len(schedule(times,keys,1)))
    def test_direction_crossing_zero_is_not_fabricated(self):
        with self.assertRaisesRegex(ValueError,'unobservable'):
            refine([0,1],{'arm':[[1,0,0],[-1,0,0]]},[dict(time=0,yaw=0)],1,1)
    def test_source_motion_without_camera_turn_is_also_refined(self):
        values=[[1,.1,0],[-1,.1,0]];times=[0,1];keys=[dict(time=0,yaw=0)]
        result=refine(times,{'arm':values},keys,1,1)
        angles=[math.degrees(math.atan2(v[1],v[0])) for v in interpolate(values,times,result)]
        self.assertLessEqual(max(abs(b-a) for a,b in zip(angles,angles[1:])),12)
        self.assertIn(.5,result)
