import unittest
from unittest.mock import Mock
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.depth_surface_checker import SurfaceChecker


class SurfaceCheckerTests(unittest.TestCase):
    def test_garment_can_be_excluded_from_planar_torso_model(self):
        doc,files=fixture();inventory={'surfaces':[dict(slot='b',role='garment_plane_candidate')]}
        checker=SurfaceChecker(Probe(doc,files,'test'),None,inventory,allow_garment_plane=False)
        with self.assertRaisesRegex(ValueError,'garment_requires_declared_surface'):
            checker.check('a','b',0,0)

    def test_partition_axes_and_baked_plane_are_preserved(self):
        doc,files=fixture();inventory={'surfaces':[dict(slot='b',role='torso')]}
        provider=Mock();axes={'a':{'axes':{'hand_l':{'length':12}}}}
        checker=SurfaceChecker(Probe(doc,files,'test'),None,inventory,
                               plane_provider=provider,source_axes=axes)
        self.assertIs(checker.plane.plane_provider,provider)
        self.assertEqual(checker.axes,axes);self.assertEqual(checker.plane.axes,axes)
        checker.plane.check=Mock(return_value={'status':'uniform_front_proxy'})
        self.assertEqual(checker.check('a','b',.5,100)['status'],'uniform_front_proxy')
        checker.plane.check.assert_called_once_with('a','b',.5,100,on_triangle=None)

    def test_unknown_visible_surface_does_not_inherit_torso_depth(self):
        doc,files=fixture();inventory={'surfaces':[dict(slot='b',role='unmodeled')]}
        checker=SurfaceChecker(Probe(doc,files,'test'),None,inventory)
        with self.assertRaisesRegex(ValueError,'surface_depth_model_unavailable:unmodeled'):
            checker.check('a','b',0,0)

    def test_no_overlap_does_not_require_an_unavailable_depth_model(self):
        doc,files=fixture(True);inventory={'surfaces':[dict(slot='b',role='unmodeled')]}
        checker=SurfaceChecker(Probe(doc,files,'test'),None,inventory)
        self.assertEqual(checker.check('a','b',0,0)['status'],'no_overlap')
