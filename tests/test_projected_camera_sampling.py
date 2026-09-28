import math
import unittest
from autospine_workbench.targets.character43.projected_camera_sampling import refine
from autospine_workbench.targets.character43.camera_sampling import schedule,interpolate
from autospine_workbench.targets.character43.camera_track import sample
from autospine_workbench.targets.character43.oblique_motion import project

class ProjectedSamplingTests(unittest.TestCase):
    def test_ankles_and_depth_share_pose_grid(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from autospine_workbench.targets.character43.projected_camera_sampling import PROFILE
        from autospine_workbench.targets.character43.camera_ankle_targets import extract
        from autospine_workbench.targets.character43.camera_depth import sample_rows
        times=[0,.5,1];keys=[dict(time=0,yaw=0),dict(time=1,yaw=360)]
        vectors={'arm':[[1,.03,0]]*3};wanted=refine(times,vectors,keys,1,1)
        source=dict(times=times,points=[[[1,2,3],[-1,2,3]]]*3,source_reference_length=1)
        bundle=SimpleNamespace(motion=dict(duration_ticks=1000000,ticks_per_second=1000000),bundle_sha256='a'*64,clip_sha256='b'*64)
        with patch('autospine_workbench.targets.character43.camera_ankle_targets.source_ankles',return_value=source),patch('autospine_workbench.targets.character43.camera_ankle_targets.source_vectors',return_value=(vectors,[[0,0,0]]*3,1)):
            ankle=extract(bundle,keys,sampling_profile=PROFILE)
        rows=[(round(t*1e6),{'foot':(1,3)}) for t in times]
        depth=sample_rows(rows,keys,PROFILE,sample_times=wanted)
        self.assertEqual(ankle['times'],wanted);self.assertEqual([t/1e6 for t,_ in depth],wanted)
        for (_,v),points in zip(depth,ankle['points']):self.assertAlmostEqual(v['foot'],points[0][2])
        with self.assertRaisesRegex(ValueError,'grid_required'):sample_rows(rows,keys,PROFILE)

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
