import unittest
from copy import deepcopy
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe, inspect, SPARSE_PROFILE


class SparseDepthTests(unittest.TestCase):
    def test_tight_cells_preserve_native_overlap_under_transforms(self):
        for transparent in (False,True):
            for angle in (-173,-47,0,17,113):
                doc,files=fixture(transparent)
                doc['bones'][0].update(rotation=angle,x=-64.3,y=127.7,scaleX=71.2,scaleY=.8)
                dense=Probe(doc,files,'test',tiled=True)
                sparse=Probe(doc,files,'test',tiled=True,sparse=True)
                tight=Probe(doc,files,'test',tiled=True,sparse='tight_triangle_boxes')
                values=[p.pair('a','b',0) for p in (dense,sparse,tight)]
                self.assertEqual(len({v['overlap_pixels'] for v in values}),1)
                self.assertGreaterEqual(tight.remaining,sparse.remaining)
                with self.assertRaisesRegex(ValueError,'cache_identity'):sparse.reuse(tight)

    def test_same_cell_disjoint_boxes_do_not_require_raster(self):
        from autospine_workbench.targets.character43.depth_sparse_tiles import regions
        attachments=[dict(triangles=[0,1,2])]*2
        points=[[(1,-1),(3,-1),(1,-3)],[(40,-40),(43,-40),(40,-43)]]
        self.assertEqual(regions([0,0,64,64],attachments,points),[[0,0,64,64]])
        self.assertEqual(regions([0,0,64,64],attachments,points,tight=True),[])

    def test_tight_bounds_union_all_triangles_and_clip_disjoint_cells(self):
        from autospine_workbench.targets.character43.depth_sparse_tiles import regions
        attachment=dict(triangles=[0,1,2,3,4,5])
        points=[(1,-1),(70,-1),(1,-5),(10,-30),(90,-30),(90,-40)]
        result=regions([0,0,128,64],[attachment]*2,[points]*2,tight=True)
        self.assertEqual(result,[[1,1,63,39],[64,1,26,39]])

    def test_opt_in_inspection_marks_its_policy_and_keeps_legacy_default(self):
        doc,files=fixture(); depth=dict(pairs=[dict(arm_slot='a',torso_slot='b',setup_front_slot='b',
            samples=[dict(tick=0,ambiguous=False,current_front_slot='b')])])
        old,_=inspect(doc,files,'test',depth)
        new,probe=inspect(doc,files,'test',depth,sparse=True)
        a=old['pairs'][0]['samples'][0]['overlap'];b=new['pairs'][0]['samples'][0]['overlap']
        self.assertEqual((a['status'],a['overlap_pixels']),(b['status'],b['overlap_pixels']))
        self.assertNotEqual(old['target_overlap']['profile'],SPARSE_PROFILE)
        self.assertEqual(new['target_overlap']['profile'],SPARSE_PROFILE)
        self.assertTrue(probe.sparse)

    def test_disconnected_geometry_preserves_exact_overlap_and_saves_budget(self):
        doc,files=fixture()
        for name in ('a','b'):
            mesh=doc['skins'][0]['attachments'][name][name]
            original=mesh['vertices'][:]
            shifted=[]
            for i in range(0,len(original),5):
                count,bone,x,y,weight=original[i:i+5]
                shifted.extend([count,bone,x+500,y+500,weight])
            mesh['vertices']+=shifted;mesh['uvs']*=2
            mesh['triangles'] += [i+4 for i in mesh['triangles'][:]]
        dense=Probe(doc,files,'test',tiled=True)
        sparse=Probe(doc,files,'test',tiled=True,sparse=True)
        a=dense.pair('a','b',0);b=sparse.pair('a','b',0)
        self.assertEqual(a['overlap_pixels'],8)
        self.assertEqual(b['overlap_pixels'],a['overlap_pixels'])
        self.assertGreater(sparse.remaining,dense.remaining)
        tiles=b['tiles'];self.assertEqual(sum(t['overlap_pixels'] for t in tiles),8)
        with self.assertRaisesRegex(ValueError,'cache_identity'):dense.reuse(sparse)

    def test_transformed_noninteger_triangles_and_transparency_match_dense(self):
        for transparent in (False,True):
            for angle in (-173,-47,17,113):
                doc,files=fixture(transparent)
                doc['bones'][0].update(rotation=angle,x=-64.3,y=127.7,scaleX=71.2,scaleY=.8)
                before=deepcopy(doc)
                a=Probe(doc,files,'test',tiled=True).pair('a','b',0)
                b=Probe(doc,files,'test',tiled=True,sparse=True).pair('a','b',0)
                self.assertEqual(a['overlap_pixels'],b['overlap_pixels'])
                self.assertEqual(doc,before)

    def test_budget_failure_is_still_unmeasured(self):
        doc,files=fixture()
        with self.assertRaisesRegex(ValueError,'pixel_budget') as error:
            Probe(doc,files,'test',tiled=True,sparse=True,pixel_budget=1).pair('a','b',0)
        self.assertEqual(error.exception.diagnostic['required_pixels'],8)
        with self.assertRaisesRegex(ValueError,'requires_tiled'):Probe(doc,files,'test',sparse=True)


if __name__=='__main__':unittest.main()
