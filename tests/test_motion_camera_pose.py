from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_oblique_motion as fixtures
from autospine_workbench.automation.motion_camera_pose import prepare,validate
from autospine_workbench.automation.motion_view_pose import prepare as fixed_prepare


class CameraPoseTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.ObliqueTests();fixture.setUp();self.bundle=SimpleNamespace(motion=fixture.base,source_kind='bvh')
        self.data=fixture.data;vectors,roots,reference=self.data
        self.centers=([(p[0]+2,p[1]+3,p[2]+4) for p in roots],reference)

    def prepare(self,keys):
        with patch('autospine_workbench.automation.motion_camera_pose.extract',return_value=self.data), \
             patch('autospine_workbench.automation.motion_camera_pose.hip_centers',return_value=self.centers):
            return prepare(self.bundle,keys)

    def test_constant_camera_retains_existing_motion_tracks(self):
        dynamic=self.prepare([{'time':0,'yaw':30}])
        with patch('autospine_workbench.automation.motion_view_pose.extract',return_value=self.data), \
             patch('autospine_workbench.automation.motion_view_pose.hip_centers',return_value=self.centers):
            fixed=fixed_prepare(self.bundle,30)
        self.assertEqual(dynamic[0]['tracks'],fixed[0]['tracks'])
        self.assertNotEqual(dynamic[0]['clip_id'],fixed[0]['clip_id'])
        validate(*dynamic)

    def test_camera_changes_are_part_of_exact_identity(self):
        duration=self.bundle.motion['duration_ticks']/self.bundle.motion['ticks_per_second']
        value=self.prepare([{'time':0,'yaw':0},{'time':duration,'yaw':10}])
        validate(*value)
        changed=deepcopy(value);changed[2]['keys'][-1]['yaw']=45
        with self.assertRaisesRegex(ValueError,'identity'):validate(*changed)
        changed=deepcopy(value);changed[0]['tracks'][0]['keys'][0]['value']+=1
        with self.assertRaisesRegex(ValueError,'identity'):validate(*changed)

    def test_full_turn_cannot_be_baked_from_only_two_source_samples(self):
        duration=self.bundle.motion['duration_ticks']/self.bundle.motion['ticks_per_second']
        with self.assertRaisesRegex(ValueError,'sampling_insufficient'):
            self.prepare([{'time':0,'yaw':0},{'time':duration,'yaw':360}])
        with self.assertRaisesRegex(ValueError,'sampling_insufficient'):
            self.prepare([{'time':0,'yaw':0},{'time':duration/2,'yaw':360},{'time':duration,'yaw':0}])

    def test_opt_in_refines_camera_without_rewriting_legacy_or_source(self):
        from autospine_workbench.targets.character43.camera_sampling import PROFILE
        original=deepcopy(self.bundle.motion)
        duration=original['duration_ticks']/original['ticks_per_second']
        keys=[dict(time=0,yaw=0),dict(time=duration,yaw=360)]
        vectors,roots,reference=deepcopy(self.data)
        # Keep a visible vertical component, so this tests temporal refinement,
        # not fabrication of an unobservable direction.
        vectors={r:[(v[0],reference,v[2]) for v in rows] for r,rows in vectors.items()}
        with patch('autospine_workbench.automation.motion_camera_pose.extract',return_value=(vectors,roots,reference)), \
             patch('autospine_workbench.automation.motion_camera_pose.hip_centers',return_value=self.centers):
            value=prepare(self.bundle,keys,sampling_profile=PROFILE)
        validate(*value)
        self.assertGreater(len(value[2]['times']),len(roots))
        self.assertEqual(self.bundle.motion,original)
        self.assertEqual(value[2]['sampling']['profile'],PROFILE)
