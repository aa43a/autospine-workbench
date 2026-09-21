import unittest
from autospine_workbench.targets.character43.depth_partition_coalesce import merge,coalesced_labels


class CoalesceTests(unittest.TestCase):
    def test_no_overlap_can_merge_but_unknown_and_opposite_cannot(self):
        self.assertEqual(merge('FNAB','NFNB'),'FFAB')
        for a,b in [('F','B'),('U','F'),('A','B'),('M','A')]:self.assertIsNone(merge(a,b))
        self.assertEqual(merge('N','U'),'U')

    def test_merged_no_overlap_does_not_bridge_conflicting_triangles(self):
        rows=[dict(body='body',time=0,status='requires_partition_or_more_depth',
            triangles={0:{'front':2},2:{'back':3},3:{'back':1},4:{'unknown':1}})]
        result,report=coalesced_labels(5,rows)
        self.assertEqual(report['original_runs'],4)
        self.assertEqual(report['coalesced_runs'],3)
        self.assertEqual([report['groups'][n] for n in result],['F','F','B','B','U'])
        self.assertEqual(report['triangle_samples'],dict(F=1,N=1,B=2,U=1))

    def test_multi_frame_conflict_is_preserved(self):
        rows=[dict(body='body',time=0,status='uniform_front_proxy',triangles={0:{'front':1}}),
              dict(body='body',time=1,status='requires_partition_or_more_depth',
                   triangles={0:{'back':1},1:{'front':1}})]
        result,report=coalesced_labels(2,rows)
        self.assertEqual(report['coalesced_runs'],2)
        self.assertEqual([report['groups'][n] for n in result],['FB','NF'])


if __name__=='__main__':unittest.main()
