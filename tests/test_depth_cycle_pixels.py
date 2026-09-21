from copy import deepcopy
import unittest
import numpy as np
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_cycle_pixels import analyze,classify,inventory


def triple():
    doc,files=fixture();doc['slots'].append(dict(name='c',bone='root',attachment='c'))
    doc['skins'][0]['attachments']['c']={'c':deepcopy(doc['skins'][0]['attachments']['a']['a'])}
    files['images/c.png']=files['images/a.png']
    cycle=dict(slots=['a','b','c','a'],edges=[dict(back=a,front=b,source='test')
               for a,b in [('a','b'),('b','c'),('c','a')]])
    return doc,files,cycle


class CyclePixelTests(unittest.TestCase):
    def test_pairwise_overlap_does_not_imply_common_pixel(self):
        masks=[np.array([v],dtype=bool) for v in [[1,0,1],[1,1,0],[0,1,1]]]
        result,common=classify(masks)
        self.assertEqual(result['status'],'spatially_distributed_cycle_support')
        self.assertEqual(result['edge_overlap_pixels'],[1,1,1]);self.assertFalse(common.any())

    def test_common_support_and_world_y_flip(self):
        doc,files,cycle=triple();before=deepcopy(doc)
        result,_=analyze(doc,files,'test',cycle,0)
        self.assertEqual(result['status'],'simultaneous_cycle_support')
        self.assertEqual(result['common_pixels'],4)
        self.assertEqual(result['common_raster_bbox'],[0,-2,2,2])
        self.assertEqual(result['common_world_samples'][0],[.5,1.5]);self.assertEqual(doc,before)

    def test_alpha_and_budget_abstention(self):
        doc,files,cycle=triple();_,transparent=fixture(True);files['images/c.png']=transparent['images/b.png']
        result,_=analyze(doc,files,'test',cycle,0)
        self.assertEqual(result['status'],'cycle_not_simultaneous_at_sample')
        self.assertEqual(result['edge_overlap_pixels'],[4,0,0])
        result,visual=analyze(doc,files,'test',cycle,0,pixel_budget=1)
        self.assertEqual(result['status'],'unmeasured');self.assertNotIn('common_pixels',result)
        self.assertIsNone(visual)

    def test_rejects_non_simple_or_mismatched_cycle(self):
        _,_,cycle=triple();cycle['edges'].reverse()
        with self.assertRaisesRegex(ValueError,'edge_inventory'):inventory(cycle)
        cycle['slots']=['a','b','a']
        with self.assertRaisesRegex(ValueError,'simple_cycle'):inventory(cycle)


if __name__=='__main__':unittest.main()
