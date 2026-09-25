import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.shoulder_region_validation import inspect,resolve_owners


class ShoulderMaterialValidationTests(unittest.TestCase):
    def test_bone_only_false_pass_is_rejected_against_moving_material(self):
        triangle=[[0.,0.],[2.,0.],[0.,2.]]
        moved=[[x+10,y] for x,y in triangle]
        row=dict(slot='sleeve',points=triangle,triangles=[[0,1,2]])
        prepared=dict(free=[0,1,2],locked=[],support=[dict(vertex=0,center=[0,0],radius=1)],context={'budget_px':20})
        def sampled(doc,animation,time):
            return (dict(torso=triangle if animation=='setup' else moved,
                         sleeve=moved if doc.get('corrected') else triangle),{})
        with patch('autospine_workbench.targets.character43.shoulder_region_validation.sample',side_effect=sampled), \
             patch('autospine_workbench.targets.character43.shoulder_region_validation.matrices',return_value={'chest':(1,0,0,1,0,0)}):
            args=({}, {}, [(row,prepared)], [0.,1.])
            self.assertTrue(inspect(*args)['passed'])
            checked=inspect(*args,material_owners={'sleeve':'torso'})
            self.assertFalse(checked['passed'])
            self.assertAlmostEqual(checked['max_region_ratio'],10)
            fixed=inspect({}, {'corrected':True}, [(row,prepared)], [0.,1.],material_owners={'sleeve':'torso'})
            self.assertTrue(fixed['passed'])
            self.assertEqual(fixed['contact_frame'],'verified_material_affine')
            with self.assertRaises(ValueError):inspect(*args,material_owners={})

    def test_empty_checks_cannot_pass(self):
        with self.assertRaises(ValueError):inspect({}, {}, [], [])

    def test_unique_source_supported_owner_is_automatic_but_ambiguity_is_not(self):
        self.assertEqual(resolve_owners([(dict(slot='arm',material_owner_candidates=['shirt']),{})]),{'arm':'shirt'})
        for candidates in ([],['shirt','cape']):
            with self.assertRaisesRegex(ValueError,'ambiguous'):
                resolve_owners([(dict(slot='arm',material_owner_candidates=candidates),{})])


if __name__=='__main__':unittest.main()
