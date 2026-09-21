import unittest
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.affine_area_repair import repair
from autospine_workbench.targets.character43.affine_pose import sample
from test_character_affine_repair import fixture


class ProjectedAreaTests(unittest.TestCase):
    def test_single_bone_uses_relative_area_not_world_scale(self):
        areas=reference([3],[[0,1,2]], [[(0,1)]]*3,[{'name':'a'}],
            {'a':(2,0,0,3,0,0)},{'a':(.2,0,0,3,0,0)})
        self.assertAlmostEqual(areas[0],.3)

    def test_opposing_rotations_do_not_normalize_away_blend_collapse(self):
        bones=[{'name':'a'},{'name':'b'}];setup={b['name']:(1,0,0,1,0,0) for b in bones}
        current={'a':(0,-1,1,0,0,0),'b':(0,1,-1,0,0,0)}
        self.assertEqual(reference([1],[[0,1,2]],[[(0,.5),(1,.5)]]*3,bones,setup,current),[1])

    def test_uniform_projection_does_not_trigger_corrective_expansion(self):
        doc=fixture()
        setup=fixture(); setup['animations']['walk']={'bones':{}}
        result,report=repair(doc,'walk',samples=3,convergent=True,
            setup_vertices=sample(setup,'walk',0)[0],projected_reference=True)
        self.assertEqual(result,doc)
        self.assertEqual(report['records'],[])

    def test_inversion_is_not_accepted_as_projection(self):
        with self.assertRaisesRegex(ValueError,'orientation'):
            reference([1],[[0,1,2]], [[(0,1)]]*3,[{'name':'a'}],
                {'a':(1,0,0,1,0,0)},{'a':(-1,0,0,1,0,0)})
