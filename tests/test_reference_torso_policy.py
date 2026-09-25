from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import math
import unittest

from autospine_workbench.automation.motion_torso_policy import select, PROFILE, REFERENCE_PROFILE
from autospine_workbench.targets.character43.torso_projection_profile import prepare
from tests.test_torso_projection import observations


class ReferenceTorsoPolicyTests(unittest.TestCase):
    def request(self, profile=REFERENCE_PROFILE):
        return dict(torso_projection_profile=profile,projection=dict(
            profile='constant-yaw-source-motion-v1',yaw_degrees=45))

    def test_explicit_reference_and_compatible_depth_required(self):
        for depth in ('external-arm-torso-depth-overlap-v2','external-arm-torso-depth-sparse-v1-experiment'):
            self.assertEqual(select(self.request(),depth),REFERENCE_PROFILE)
        with self.assertRaisesRegex(Exception,'requires_projection'):
            select({'torso_projection_profile':REFERENCE_PROFILE},'external-arm-torso-depth-overlap-v2')
        with self.assertRaisesRegex(Exception,'requires_overlap_depth'):
            select(self.request(),'external-regional-depth-order-v1')

    def test_reference_keeps_constant_foreshortening_and_provenance(self):
        bundle=SimpleNamespace(bundle_sha256='a'*64,clip_sha256='b'*64)
        request=self.request();before=deepcopy(request)
        def anchors(_,yaw):return [observations(yaw)]*2,[0,1000000]
        with patch('autospine_workbench.targets.character43.torso_projection_profile.anchors',side_effect=anchors):
            report=prepare(bundle,request)
            old=prepare(bundle,self.request(PROFILE))
        self.assertAlmostEqual(report['records'][0]['transverse'],math.cos(math.radians(45)))
        self.assertEqual(old['records'][0]['transverse'],1)
        self.assertEqual(report['source_bundle_sha256'],'a'*64)
        self.assertEqual(report['source_motion_sha256'],'b'*64)
        self.assertEqual(report['reference_source_yaw'],0)
        self.assertEqual(report['yaw_degrees'],45)
        self.assertEqual(request,before)

    def test_different_reference_timebase_rejected(self):
        def anchors(_,yaw):return [observations(yaw)]*2,[0,1000000 if yaw else 2000000]
        with patch('autospine_workbench.targets.character43.torso_projection_profile.anchors',side_effect=anchors):
            with self.assertRaisesRegex(ValueError,'times_mismatch'):
                prepare(object(),self.request())
