import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.depth_surface_checker import SurfaceChecker


class SurfaceCheckerTests(unittest.TestCase):
    def test_unknown_visible_surface_does_not_inherit_torso_depth(self):
        doc,files=fixture();inventory={'surfaces':[dict(slot='b',role='unmodeled')]}
        checker=SurfaceChecker(Probe(doc,files,'test'),None,inventory)
        with self.assertRaisesRegex(ValueError,'surface_depth_model_unavailable:unmodeled'):
            checker.check('a','b',0,0)

    def test_no_overlap_does_not_require_an_unavailable_depth_model(self):
        doc,files=fixture(True);inventory={'surfaces':[dict(slot='b',role='unmodeled')]}
        checker=SurfaceChecker(Probe(doc,files,'test'),None,inventory)
        self.assertEqual(checker.check('a','b',0,0)['status'],'no_overlap')
