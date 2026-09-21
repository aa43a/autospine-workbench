import random
import unittest
from autospine_workbench.targets.character43.motion_depth_order import _crossing_ranges,_crosses


class CrossingRangeTests(unittest.TestCase):
    def test_index_matches_original_predicate_for_every_slot_pair(self):
        rng=random.Random(17)
        for count in (2,5,19,43):
            slots=[str(i) for i in range(count)];indices={s:i for i,s in enumerate(slots)}
            requests=[]
            for _ in range(count*3):
                a,b=rng.sample(range(count),2)
                requests.append((slots[a],min(a,b),max(a,b)))
            ranges=_crossing_ranges(requests)
            for i,a in enumerate(slots):
                for b in slots[i+1:]:
                    original=any((a==arm and lo<=indices[b]<=hi) or
                                 (b==arm and lo<=indices[a]<=hi) for arm,lo,hi in requests)
                    self.assertEqual(_crosses(a,b,indices,ranges),original)

    def test_no_requests_and_two_sided_interval(self):
        self.assertFalse(_crosses('a','b',{'a':0,'b':1},_crossing_ranges([])))
        ranges=_crossing_ranges([('b',0,1),('b',1,4),('b',1,2)])
        self.assertEqual(ranges,{'b':(0,4)})
