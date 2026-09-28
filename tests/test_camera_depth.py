from types import SimpleNamespace
from unittest.mock import patch
import unittest
from autospine_workbench.targets.character43.motion_depth import _source, build
from autospine_workbench.targets.character43.camera_depth import receipt
from autospine_workbench.targets.character43.oblique_motion import project
from test_motion_depth import fixture


class CameraDepthTests(unittest.TestCase):
    def test_orbit_reverses_depth_without_collapsing_a_full_turn(self):
        point=(3.,2.,-1.)
        frames=[SimpleNamespace(tick=i*250000,joints=[('wrist',SimpleNamespace(screen_xy=point[:2],depth=point[2]))])
                for i in range(5)]
        keys=[dict(time=0,yaw=0),dict(time=1,yaw=360)]
        with patch('autospine_workbench.targets.character43.motion_depth.project_bvh_frames',return_value=SimpleNamespace(frames=frames)):
            rows,_,_=_source(SimpleNamespace(source_sha256='a'*64),{'root':{'reference_length_source_units':2}},None,camera_keys=keys)
        for i,(_,values) in enumerate(rows):
            self.assertAlmostEqual(values['wrist'],project(point,i*90)[2])
        self.assertAlmostEqual(rows[0][1]['wrist'],-rows[2][1]['wrist'])
        self.assertAlmostEqual(rows[0][1]['wrist'],rows[4][1]['wrist'])

    def test_camera_evidence_retains_source_ticks_when_clipped(self):
        doc,mapping=fixture();keys=[dict(time=0,yaw=0),dict(time=1,yaw=360)]
        frames=[(i*250000,dict(torso=0,shoulder=1,elbow=1,wrist=1)) for i in range(5)]
        with patch('autospine_workbench.targets.character43.motion_depth._source',return_value=(frames,1,'a'*64)):
            report=build(doc,None,mapping,camera_keys=keys,clip_bounds=(250000,750000))
        self.assertEqual(report['camera']['samples'][2],dict(source_tick=500000,yaw_degrees=180))
        self.assertEqual(report['pairs'][0]['samples'][0]['source_tick'],250000)
        self.assertEqual(report['pairs'][0]['samples'][0]['tick'],0)
        self.assertFalse(report['selected'])
        self.assertNotEqual(receipt(keys,[0,1000000])['track_sha256'],receipt([dict(time=0,yaw=0)],[0,1000000])['track_sha256'])

    def test_conflicting_and_invalid_cameras_fail(self):
        doc,mapping=fixture()
        with self.assertRaisesRegex(ValueError,'camera_conflict'):
            build(doc,None,mapping,yaw_degrees=0,camera_keys=[dict(time=0,yaw=0)])
        with self.assertRaisesRegex(ValueError,'camera_track'):
            receipt([dict(time=0,yaw=float('nan'))],[0,1000000])
