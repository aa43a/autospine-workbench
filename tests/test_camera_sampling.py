import unittest
from autospine_workbench.targets.character43.camera_sampling import schedule,interpolate
from autospine_workbench.targets.character43.camera_track import sample

class CameraSamplingTests(unittest.TestCase):
    def test_hidden_round_trip_retains_original_frames_and_turns(self):
        keys=[dict(time=0,yaw=0),dict(time=.013579,yaw=360),dict(time=.028765,yaw=0)]
        times=[0,.033333,.066667,.1]
        wanted=schedule(times,keys,.1)
        self.assertTrue(set(times)<=set(wanted));self.assertIn(.013579,wanted);self.assertIn(.028765,wanted)
        self.assertGreater(len(wanted),50)
        self.assertLess(max(abs(sample(keys,b)-sample(keys,a)) for a,b in zip(wanted,wanted[1:])),15)
    def test_world_interpolation_preserves_samples_and_never_extrapolates(self):
        values=[[[1,2,3],[5,6,7]],[[3,4,5],[7,8,9]]]
        self.assertEqual(interpolate(values,[0,1],[0,.5,1]),[values[0],[[2,3,4],[6,7,8]],values[1]])
        with self.assertRaisesRegex(ValueError,'extrapolation'):interpolate(values,[0,1],[2])
    def test_budget_and_tick_resolution_are_explicit_failures(self):
        keys=[dict(time=i/255,yaw=3600 if i%2 else -3600) for i in range(256)]
        with self.assertRaisesRegex(ValueError,'budget'):schedule([0,1],keys,1)
        with self.assertRaisesRegex(ValueError,'resolution'):schedule([0,.000001],[dict(time=0,yaw=0),dict(time=.000001,yaw=360)],.000001)
    def test_slow_native_track_is_unchanged(self):
        self.assertEqual(schedule([0,.5,1],[dict(time=0,yaw=0),dict(time=1,yaw=10)],1),[0,.5,1])

    def test_depth_and_ankles_use_the_identical_refined_grid(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from autospine_workbench.targets.character43.camera_sampling import PROFILE
        from autospine_workbench.targets.character43.camera_depth import sample_rows
        from autospine_workbench.targets.character43.camera_ankle_targets import extract
        keys=[dict(time=0,yaw=0),dict(time=.013579,yaw=360),dict(time=.028765,yaw=0)]
        times=[0,.033333,.066667,.1];points=[[[3,2,-1],[-3,2,-1]] for _ in times]
        source=dict(times=times,points=points,source_reference_length=10)
        bundle=SimpleNamespace(bundle_sha256='a'*64,clip_sha256='b'*64,motion=dict(duration_ticks=100000,ticks_per_second=1000000))
        with patch('autospine_workbench.targets.character43.camera_ankle_targets.source_ankles',return_value=source), \
             patch('autospine_workbench.targets.character43.camera_ankle_targets.source_vectors',return_value=({},[(0,0,0)]*4,10)):
            ankles=extract(bundle,keys,sampling_profile=PROFILE)
        depth=sample_rows([(round(t*1e6),{'foot':(3,-1)}) for t in times],keys,PROFILE)
        self.assertEqual(ankles['times'],[t/1e6 for t,_ in depth])
        self.assertEqual(ankles['times'],schedule(times,keys,.1))
        for (_,row),p in zip(depth,ankles['points']):self.assertAlmostEqual(row['foot'],p[0][2])
