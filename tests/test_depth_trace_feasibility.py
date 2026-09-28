import unittest
from autospine_workbench.targets.character43.depth_trace_feasibility import inspect


def row(front=0,back=0,ambiguous=0,unknown=0):
    return dict(front=front,back=back,ambiguous=ambiguous,unknown=unknown)


class TraceFeasibilityTests(unittest.TestCase):
    def test_stable_back_requires_all_hypotheses(self):
        result=inspect([dict(triangles={'0':row(back=4)})]*4,2)
        self.assertEqual(result['counts'],{'stable_back':1})
        self.assertTrue(result['existing_triangle_split_fully_decidable'])

    def test_opposing_pixels_cannot_be_repaired_by_reordering_whole_triangle(self):
        result=inspect([dict(triangles={'0':row(front=2,back=2)})],1)
        self.assertTrue(result['requires_subtriangle_or_model_change'])
        self.assertFalse(result['existing_triangle_split_fully_decidable'])

    def test_model_disagreement_remains_unresolved(self):
        result=inspect([dict(triangles={'0':row(front=4)}),dict(triangles={'0':row(back=4)})],1)
        self.assertEqual(result['counts'],{'unresolved':1})
        self.assertFalse(result['requires_subtriangle_or_model_change'])

    def test_missing_trace_or_changed_overlap_rejects(self):
        with self.assertRaisesRegex(ValueError,'missing_trace'):inspect([{}],1)
        with self.assertRaisesRegex(ValueError,'hypothesis_coverage'):
            inspect([dict(triangles={'0':row(front=4)}),dict(triangles={})],1)
