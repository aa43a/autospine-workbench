import unittest
from m4_cloth_material_neighborhood import anchors, classify, duration
from autospine_workbench.targets.character43.skirt_motion_contact import transport


class MaterialNeighborhoodTests(unittest.TestCase):
    def test_same_material_follows_deformation_not_screen_coordinates(self):
        grid=anchors([[0,0],[10,0],[0,10]],[0,1,2],[2,2],0,1)
        self.assertEqual(transport([[5,1],[25,1],[5,21]],grid[0]['anchor']),[9.,5.])

    def test_uncovered_samples_are_retained(self):
        grid=anchors([[0,0],[2,0],[0,2]],[0,1,2],[0,0],2,2)
        self.assertEqual(len(grid),9)
        self.assertTrue(any(r['anchor'] is None for r in grid))

    def test_support_does_not_relabel_visible_calf_or_transparent_material(self):
        self.assertEqual(classify(255,0,0,{'triangle':1}),'originally_uncovered_material')
        self.assertEqual(classify(2,255,0,None),'low_alpha_limb_material')
        self.assertEqual(classify(255,255,0,None),'no_bounded_sliding_support')
        self.assertEqual(classify(255,255,0,{'triangle':1}),'bounded_sliding_support')

    def test_duration_from_animation_tracks(self):
        self.assertEqual(duration({'bones':{'leg':{'rotate':[{'time':0},{'time':3.5}]}}}),3.5)
