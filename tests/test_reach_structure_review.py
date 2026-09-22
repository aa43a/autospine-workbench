import unittest
from m4_reach_structure_review import summarize


class StructureTests(unittest.TestCase):
    def test_mixed_group_not_misreported_as_uniform(self):
        samples=[dict(body='chest',time=0,status='requires_partition_or_more_depth',
                      triangles={0:{'front':3},1:{'back':4}})]
        report=summarize(['upperarm','upperarm','hand'],samples)
        self.assertEqual(report['groups'],{'hand':{'N':1},'upperarm':{'M':1}})
        self.assertEqual(report['frames'][0]['marked'],[[0,'F'],[1,'B']])

    def test_duplicate_frame_rejected(self):
        row=dict(body='chest',time=0,status='no_overlap',triangles={})
        with self.assertRaises(ValueError): summarize(['upperarm'],[row,row])

    def test_unknown_not_promoted(self):
        row=dict(body='chest',time=0,status='requires_partition_or_more_depth',triangles={0:{'unknown':1,'front':4}})
        self.assertEqual(summarize(['hand'],[row])['groups']['hand'],{'U':1})
