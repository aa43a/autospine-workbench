import unittest
from m4_reach_depth_review import intervals


class ReachDepthReviewTests(unittest.TestCase):
    def test_unmeasured_and_hidden_samples_break_visible_intervals(self):
        rows=[]
        for i,(status,pixels,ambiguous,front) in enumerate([
            ('sampled',3,True,'arm'),('sampled',4,True,'body'),
            ('unmeasured',0,False,'body'),('sampled',0,True,'arm'),
            ('sampled',2,False,'body'),('sampled',2,False,'arm')]):
            rows.append(dict(tick=i*100000,overlap=dict(status=status,overlap_pixels=pixels),
                             ambiguous=ambiguous,current_front_slot=front))
        result=intervals(rows)
        self.assertEqual([r['count'] for r in result],[2,1,1,1,1])
        self.assertEqual(result[0]['end'],.1)
        self.assertEqual([r['key'][0] for r in result],['straddling','unmeasured','no_overlap','measured','measured'])
        self.assertNotEqual(result[-1]['key'],result[-2]['key'])

    def test_empty_has_no_invented_interval(self):
        self.assertEqual(intervals([]),[])
