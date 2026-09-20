import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support
from autospine_workbench.targets.character43.depth_raster_tiles import tiles
from autospine_workbench.targets.spine43.seam_raster import mask


def large_fixture():
    doc,files=fixture(); doc['bones'][0].update(scaleX=300,scaleY=300,length=2)
    return doc,files


class RasterTileTests(unittest.TestCase):
    def test_unknown_triangle_classification_matches_untiled_across_seams(self):
        doc,files=large_fixture(); doc['bones'][0].update(scaleX=200,scaleY=200)
        values=[[.1,.2],None,[.1,.2],[.1,.2]]
        options=dict(depth_intervals=values)
        direct=overlap_support(Probe(doc,files,'test'),'a','b',0,{'root':(.1,.2)},**options)
        tiled=overlap_support(Probe(doc,files,'test',tiled=True),'a','b',0,{'root':(.1,.2)},**options)
        self.assertEqual(tiled['counts'],direct['counts'])
        self.assertEqual(tiled['status'],direct['status'])
        self.assertGreater(tiled['counts']['unknown'],0)

    def test_large_roi_matches_direct_raster_across_tile_boundaries(self):
        doc,files=large_fixture(); probe=Probe(doc,files,'test',tiled=True)
        result=probe.pair('a','b',0)
        self.assertGreater(result['roi'][2]*result['roi'][3],262144)
        mesh=doc['skins'][0]['attachments']['a']['a']
        direct=mask(mesh,probe.positions[0]['a'],probe.textures['a'],result['roi'])>=8
        self.assertEqual(result['overlap_pixels'],int(direct.sum()))
        self.assertEqual(sum(t['roi'][2]*t['roi'][3] for t in result['tiles']),360000)
        self.assertEqual(probe.remaining,64_000_000-720000)
        cached=probe.cached_common('a','b',0,result['tiles'][0]['roi'])
        self.assertIsNotNone(cached)
        self.assertFalse(cached.flags.writeable)
        self.assertIsNone(probe.cached_common('a','b',1,result['tiles'][0]['roi']))
        classification=overlap_support(probe,'a','b',0,{'root':(.1,.2)})
        self.assertEqual(classification['counts']['front'],int(direct.sum()))
        self.assertEqual(classification['status'],'uniform_front_proxy')
        probe.pair('a','b',.1)
        self.assertIsNone(probe.cached_common('a','b',0,result['tiles'][0]['roi']))
        with self.assertRaisesRegex(ValueError,'pixel_budget'): Probe(doc,files,'test').pair('a','b',0)

    def test_tiling_does_not_bypass_aggregate_budget_or_cache_policy(self):
        doc,files=large_fixture(); probe=Probe(doc,files,'test',tiled=True,pixel_budget=100)
        with self.assertRaisesRegex(ValueError,'pixel_budget') as error: probe.pair('a','b',0)
        self.assertEqual(error.exception.diagnostic['limit_kind'],'aggregate_budget')
        self.assertEqual(probe.results,{})
        with self.assertRaisesRegex(ValueError,'cache_identity'):
            probe.reuse(Probe(doc,files,'test'))
        with self.assertRaisesRegex(ValueError,'tile_limit'): tiles([0,0,4096,4096])

    def test_negative_origin_and_partial_edge_tiles(self):
        parts=tiles([-17,-19,513,257])
        self.assertEqual(len(parts),6)
        self.assertEqual(sum(w*h for x,y,w,h in parts),513*257)
        self.assertEqual(parts[-1],[495,237,1,1])


if __name__=='__main__': unittest.main()
