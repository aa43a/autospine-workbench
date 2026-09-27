import unittest
from autospine_workbench.targets.character43.terminal_transverse_transition import gains
from autospine_workbench.targets.character43.limb_transverse_repair import build
from autospine_workbench.targets.character43.affine_pose import sample
from test_limb_transverse_repair import fixture


class TerminalTransverseTransitionTests(unittest.TestCase):
    def test_scale_independent_smooth_transition_and_terminal_zero(self):
        for scale in (1,10):
            doc=fixture();doc['bones'][3]['x']=20*scale
            doc['skins'][0]['attachments']['leg']['leg']['vertices']=[v for x in (15,17.5,20)
                for v in (1,2,x*scale,2*scale,1.)]
            self.assertEqual(gains(doc,'leg',.25),[1.,.5,0.])

    def test_retains_parent_at_terminal_and_preserves_other_attachments(self):
        doc=fixture();doc['bones'][3]['x']=20
        doc['skins'][0]['attachments']['leg']['leg']['vertices']=[v for x,y in ((15,2),(17.5,3),(20,4)) for v in (1,2,x,y,1.)]
        result,report=build(doc,'motion',['leg'],anchor_terminal=True,terminal_transition=.25,required_times=[.371])
        before=sample(doc,'motion',.371)[0];after=sample(result,'motion',.371)[0]
        self.assertEqual(before['leg'][2],after['leg'][2]);self.assertEqual(before['other'],after['other'])
        self.assertNotEqual(before['leg'][0],after['leg'][0])
        self.assertIn('spatial_taper_does_not_preserve_triangle_area',report['limitations'])
        self.assertEqual(result['bones'],doc['bones']);self.assertEqual(result['skins'],doc['skins'])

    def test_rejects_invalid_fraction_and_nonaxial_chain(self):
        doc=fixture()
        for fraction in (0,2,float('nan')):
            with self.assertRaises(ValueError):gains(doc,'leg',fraction)
        doc['bones'][3]['y']=1
        with self.assertRaisesRegex(ValueError,'nonaxial'):gains(doc,'leg',.25)
