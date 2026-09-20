from copy import deepcopy
import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_proxy_unknown import inspect
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


class UnknownDepthTests(unittest.TestCase):
    def test_missing_and_outside_range_are_distinct_and_source_unchanged(self):
        doc,files=fixture(); doc['bones'][0]['length']=1; before=deepcopy(doc)
        missing=inspect(Probe(doc,files,'test'),'a','b',0,{})
        outside=inspect(Probe(doc,files,'test'),'a','b',0,{'root':(0,.1)})
        self.assertEqual(missing['causes'][0]['reason'],'missing_segment')
        self.assertEqual(outside['causes'][0]['reason'],'outside_quarter_cap')
        self.assertEqual(outside['causes'][0]['overlap_pixels'],4)
        self.assertTrue(all(v['x_ratio']==2 for v in outside['causes'][0]['supporting_vertices']))
        self.assertEqual(doc,before)

    def test_transparent_and_known_are_not_unknown(self):
        doc,files=fixture(True)
        self.assertEqual(inspect(Probe(doc,files,'test'),'a','b',0,{})['causes'],[])
        doc,files=fixture(); doc['bones'][0]['length']=2
        self.assertEqual(inspect(Probe(doc,files,'test'),'a','b',0,{'root':(0,.1)})['causes'],[])


if __name__=='__main__': unittest.main()
