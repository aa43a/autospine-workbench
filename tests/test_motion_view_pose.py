from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_oblique_motion as fixtures
from autospine_workbench.automation.motion_view_pose import prepare, validate
from autospine_workbench.targets.character43.oblique_motion import project


class ViewPoseTests(unittest.TestCase):
    def prepared(self, yaw):
        fixture=fixtures.ObliqueTests();fixture.setUp()
        vectors,roots,reference=fixture.data
        centers=[(p[0]+2,p[1]+3,p[2]+4) for p in roots]
        with patch('autospine_workbench.automation.motion_view_pose.extract',return_value=fixture.data), \
             patch('autospine_workbench.automation.motion_view_pose.hip_centers',return_value=(centers,reference)):
            result=prepare(SimpleNamespace(motion=fixture.base,source_kind='bvh'),yaw)
        return result,vectors,centers

    def test_one_view_for_hip_and_limb_and_motion_identity(self):
        (motion,view,pose),vectors,centers=self.prepared(-45)
        validate(pose,motion,view,None)
        self.assertEqual(pose['hip_centers'],[project(c,-45) for c in centers])
        role=next(iter(vectors))
        self.assertEqual(pose['vectors'][role],[project(v,-45) for v in vectors[role]])
        self.assertEqual(view['motion_sha256'],pose['motion_sha256'])

    def test_other_camera_or_clipped_time_cannot_reuse_pose(self):
        (motion,view,pose),_,_=self.prepared(-45)
        wrong=deepcopy(view);wrong['yaw_degrees']=0
        for camera,time_range in ((wrong,None),(None,None),(view,(0,1))):
            with self.assertRaisesRegex(ValueError,'camera_mismatch'):
                validate(pose,motion,camera,time_range)

    def test_zero_view_preserves_source_coordinates(self):
        (_,_,pose),vectors,centers=self.prepared(0)
        self.assertEqual(pose['vectors'],vectors)
        self.assertEqual(pose['hip_centers'],centers)
