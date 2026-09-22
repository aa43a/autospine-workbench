import unittest
from autospine_workbench.targets.character43.area_preservation import minimum_ratios
from autospine_workbench.targets.character43.raw_compression_preservation import CONTRACT, floors


class RawCompressionTests(unittest.TestCase):
    def test_compressed_area_above_projection_is_preserved(self):
        values=floors([[0,0],[1,0],[0,.4]],[[0,1,2]],[.15],[.5])
        self.assertAlmostEqual(values[0],4/3)
        context=dict(row={'triangles':[[0,1,2]]},minimum_ratios=values)
        with self.assertRaisesRegex(ValueError,'invalid_floors'):minimum_ratios(context)
        self.assertEqual(minimum_ratios(dict(context,area_floor_contract=CONTRACT)),values)

    def test_inversion_is_not_preserved_and_existing_expansion_is_not_locked(self):
        for height in (-.4,3):
            value=floors([[0,0],[1,0],[0,height]],[[0,1,2]],[.5],[.5])[0]
            self.assertEqual(value,.5 if height<0 else 1)

    def test_conflicting_ceiling_and_orientation_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError,'ceiling'):
            floors([[0,0],[1,0],[0,.4]],[[0,1,2]],[.05],[.5])
        with self.assertRaisesRegex(ValueError,'orientation'):
            floors([[0,0],[1,0],[0,.4]],[[0,1,2]],[-.15],[.5])

    def test_unknown_contract_rejected(self):
        with self.assertRaisesRegex(ValueError,'unknown_contract'):
            minimum_ratios(dict(area_floor_contract='typo',row={'triangles':[]}))

    def test_solver_restores_compressed_triangle_above_projected_reference(self):
        from autospine_workbench.targets.character43.area_projection import project
        points=[[0,0],[1,0],[0,.4]];triangles=[[0,1,2]]
        context=dict(row={'triangles':triangles},areas=[.15],free=[False,False,True],
            budget=.3,edges=[(0,1),(0,2),(1,2)],lengths=[1,.4,1.0770329614],
            minimum_ratios=floors(points,triangles,[.15],[.5]),area_floor_contract=CONTRACT)
        corrected,result=project(context,points,initial=[[0,0],[1,0],[0,.2]])
        self.assertTrue(result['converged'])
        self.assertGreaterEqual(corrected[2][1],.4-1e-7)
        self.assertEqual(corrected[:2],points[:2])
