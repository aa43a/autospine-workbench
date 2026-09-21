from copy import deepcopy
from types import SimpleNamespace
import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.depth_region_partition import build
from autospine_workbench.targets.character43.depth_partition_compact import compact
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.depth_shared_boundary import BoundaryProbe,intersection_area


class SharedBoundaryTests(unittest.TestCase):
    def test_shared_diagonal_contact_is_refined_without_editing_raster_result(self):
        doc,files=fixture();split,receipt=build(doc,['a'],triangle_labels={'a':['x','y']});split,receipt=compact(split,receipt)
        a,b=[r['slot'] for r in receipt['regions']];probe=Probe(split,files,'test')
        original=deepcopy(probe.pair(a,b,0));self.assertGreater(original['overlap_pixels'],0)
        wrapped=BoundaryProbe(probe,receipt)
        self.assertEqual(wrapped.pair(a,b,0)['overlap_pixels'],0)
        self.assertEqual(probe.pair(a,b,0),original)
        self.assertGreater(wrapped.pair(a,'b',0)['overlap_pixels'],0)
        self.assertEqual(BoundaryProbe(probe,receipt,pair_limit=0).pair(a,b,0),original)

    def test_positive_area_and_degeneracy_are_not_disjoint(self):
        a=[[0,0],[2,0],[0,2]]
        self.assertEqual(intersection_area(a,[[2,0],[2,2],[0,2]]),0)
        self.assertAlmostEqual(intersection_area(a,a),2)
        self.assertAlmostEqual(intersection_area(a,list(reversed(a))),2)
        self.assertIsNone(intersection_area(a,[[0,0],[1,0],[2,0]]))
        self.assertGreater(intersection_area(a,[[1,0],[2,0],[1,1]]),0)

    def test_same_source_folded_neighbor_retains_overlap(self):
        mesh={'triangles':[0,1,2]}
        document={'skins':[{'attachments':{'a':{'a':mesh},'b':{'b':mesh}}}]}
        # Both triangles share edge 0--1 but lie on the same side after bending.
        points={'a':[[0,0],[2,0],[0,2]],'b':[[0,0],[2,0],[1,1]]}
        original={'status':'sampled','overlap_pixels':2}
        base=SimpleNamespace(document=document,positions={0:points},remaining=100,
            slots={s:{'attachment':s} for s in points},pair=lambda *args:original)
        regions={'regions':[{'slot':s,'source_slot':'arm','source_vertex_indices':ids}
                            for s,ids in [('a',[0,1,2]),('b',[0,1,3])]]}
        wrapped=BoundaryProbe(base,regions)
        self.assertEqual(wrapped.pair('a','b',0),original)
        self.assertEqual(wrapped.records,[])
        # A mismatched copy of a shared source vertex is not a common boundary.
        points['b']=[[0,-1],[2,0],[0,-2]]
        self.assertEqual(BoundaryProbe(base,regions).pair('a','b',0),original)


if __name__=='__main__':unittest.main()
