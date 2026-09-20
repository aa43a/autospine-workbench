import unittest
from unittest.mock import Mock,patch
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.torso_depth_refinement import Checker

MODULE='autospine_workbench.targets.character43.torso_depth_refinement.'


class TorsoPlaneChecks(unittest.TestCase):
    def test_transparent_overlap_needs_no_invented_depth(self):
        doc,files=fixture(True); sampler=Mock()
        check=Checker(Probe(doc,files,'test'),sampler).check('a','b',0,200000)
        self.assertEqual(check['status'],'no_overlap')
        sampler.assert_not_called()

    def test_plane_changes_relative_depth_with_original_mesh_preserved(self):
        doc,files=fixture(); doc['bones'][0]['length']=2
        sampler=Mock(return_value={'root':(.2,.2)})
        with patch(MODULE+'observe',return_value={'segments':{}}), \
             patch(MODULE+'at',return_value={'coefficients':[0,0,.3]}):
            check=Checker(Probe(doc,files,'test'),sampler).check('a','b',0,200000)
        self.assertEqual(check['status'],'uniform_back_proxy')
        self.assertEqual(check['counts']['back'],4)
        self.assertEqual(doc['bones'][0]['length'],2)

    def test_degenerate_plane_is_not_treated_as_no_overlap(self):
        doc,files=fixture(); doc['bones'][0]['length']=2
        with patch(MODULE+'observe',return_value={'segments':{}}), \
             patch(MODULE+'at',side_effect=ValueError('cloth_plane_projected_anchors_degenerate')):
            with self.assertRaisesRegex(ValueError,'anchors_degenerate'):
                Checker(Probe(doc,files,'test'),Mock(return_value={})).check('a','b',0,0)


if __name__=='__main__': unittest.main()
