import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_pair_depth import compare


class MeshPairPixelDepthTests(unittest.TestCase):
    def test_parallel_depth_gradients_resolve_coarse_false_ambiguity(self):
        doc,files=fixture();a=[[v,v] for v in (0,1,1,0)];b=[[v-.1,v-.1] for v in (0,1,1,0)]
        coarse=compare(Probe(doc,files,'test'),'a','b',0,a,b)
        fine=compare(Probe(doc,files,'test'),'a','b',0,a,b,pixelwise=True)
        self.assertEqual(coarse['status'],'requires_partition_or_more_depth')
        self.assertEqual(fine['status'],'uniform_front_proxy')
        self.assertEqual(fine['counts']['front'],fine['overlap_pixels'])

    def test_unknowns_remain_unknown_in_pixelwise_mode(self):
        doc,files=fixture()
        result=compare(Probe(doc,files,'test'),'a','b',0,[[1,1],None,[1,1],[1,1]],[[0,0]]*4,pixelwise=True)
        self.assertGreater(result['counts']['unknown'],0)

    def test_wide_intervals_do_not_collapse_to_their_midpoint(self):
        doc,files=fixture()
        result=compare(Probe(doc,files,'test'),'a','b',0,[[0,1]]*4,[[.2,.3]]*4,pixelwise=True)
        self.assertEqual(result['counts']['ambiguous'],result['overlap_pixels'])

    def test_pixelwise_results_match_across_tiles(self):
        doc,files=fixture()
        for attachments in doc['skins'][0]['attachments'].values():
            mesh=next(iter(attachments.values()));mesh['vertices']=list(mesh['vertices'])
            mesh['vertices'][7]=600;mesh['vertices'][12]=600
        results=[]
        for tiled,sparse in ((False,False),(True,False),(True,True)):
            results.append(compare(Probe(doc,files,'test',tiled=tiled,sparse=sparse),'a','b',0,
                [[v,v] for v in (0,1,1,0)],[[v-.1,v-.1] for v in (0,1,1,0)],pixelwise=True)['counts'])
        self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])
