import unittest
from autospine_workbench.asset.planning.sleeve_motion_envelope import MOTIONS,angles,track,build
from tests.test_sleeve_helpers import SleeveHelperTests
from autospine_workbench.asset.planning.sleeve_helpers import make_helper


class SleeveEnvelopeTests(unittest.TestCase):
    def test_fixed_limits_setup_loop_and_combination_extrema(self):
        self.assertEqual(len(MOTIONS),7)
        self.assertEqual(MOTIONS[:3],(('forearm',(30,0,0)),('hand',(0,30,0)),('cloth',(0,0,10))))
        for _,amplitudes in MOTIONS:
            self.assertEqual(angles(amplitudes,32),list(amplitudes))
            self.assertEqual(angles(amplitudes,96),[-a for a in amplitudes])
            for tick in (0,64,128):self.assertEqual(angles(amplitudes,tick),[0.,0.,0.])
        with self.assertRaises(ValueError):angles((30,30,10),129)
        with self.assertRaises(ValueError):build({}, {'bones':[]})

    def test_branch_fk_combined_loop_and_fixed_interface(self):
        mesh,bones=SleeveHelperTests().fixture()
        helper,weights,cloth=make_helper(mesh,bones,[['hanging_cloth']]*3,'cloth')
        row=dict(setup_vertices=mesh['vertices_xy'],weights=weights,triangles=[[0,1,2]],
                 cloth_vertices=cloth,interface_root=dict(edges=[[0,1]]))
        result=track(row,bones+[helper],'combined',(30,-30,10))
        self.assertEqual(len(result['qa']),129);self.assertEqual(len(result['samples']),33)
        self.assertEqual(result['anchor_displacement'],0)
        self.assertLess(result['loop_error'],1e-9)
        self.assertEqual(result['failed_ticks'],0)
        self.assertNotEqual(result['samples'][8]['points'],result['samples'][0]['points'])
