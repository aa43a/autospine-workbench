import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe
from autospine_workbench.targets.character43.mesh_pair_depth import compare
from test_source_depth_sampler import sampler


class MeshPairDepthTests(unittest.TestCase):
    def check(self,a,b):
        doc,files=fixture()
        return compare(Probe(doc,files,'test'),'a','b',0,a,b)

    def test_separated_intervals_and_reverse_order(self):
        a=[[.2,.3]]*4; b=[[0,.1]]*4
        self.assertEqual(self.check(a,b)['status'],'uniform_front_proxy')
        self.assertEqual(self.check(b,a)['status'],'uniform_back_proxy')

    def test_unknown_triangle_cannot_be_hidden_by_known_triangle(self):
        result=self.check([[.2,.3],None,[.2,.3],[.2,.3]],[[0,.1]]*4)
        self.assertGreater(result['counts']['unknown'],0)
        self.assertEqual(result['unknown_support']['a'],result['counts']['unknown'])
        self.assertEqual(result['unknown_support']['b'],0)
        self.assertEqual(result['status'],'requires_partition_or_more_depth')

    def test_entire_envelope_must_clear_margin(self):
        result=self.check([[.01,.3]]*4,[[0,.1]]*4)
        self.assertEqual(result['counts']['ambiguous'],4)
        with self.assertRaisesRegex(ValueError,'intervals_invalid'):
            self.check([[.3,.2]]*4,[[0,.1]]*4)

    def test_budget_failure_is_explicit(self):
        doc,files=fixture(); probe=Probe(doc,files,'test',pixel_budget=8)
        with self.assertRaisesRegex(ValueError,'pixel_budget'):
            compare(probe,'a','b',0,[[.2,.3]]*4,[[0,.1]]*4)

    def test_leg_axes_use_declared_source_endpoints(self):
        source=sampler(); depths=source.joint_depths(250000)
        segments=source.leg_segments(250000)
        self.assertEqual(set(segments),{'thigh_l','calf_l','thigh_r','calf_r'})
        for side,suffix in [('left','l'),('right','r')]:
            role=source.roles['humanoid.leg.upper.'+side]
            self.assertEqual(segments['thigh_'+suffix],tuple(depths[n] for n in
                (role['joint_name'],role['aim']['joint_name'])))
        self.assertNotIn('thigh_l',source(250000))

    def test_tiled_triangle_trace_matches_aggregate_and_retains_unknown(self):
        from collections import Counter
        doc,files=fixture();a=[[.2,.3],None,[.2,.3],[.2,.3]];b=[[0,.1]]*4
        expected=compare(Probe(doc,files,'test'),'a','b',0,a,b)
        rows={}
        def collect(triangle,values):rows.setdefault(triangle,Counter()).update(values)
        result=compare(Probe(doc,files,'test',tiled=True,sparse=True),'a','b',0,a,b,on_triangle=collect)
        self.assertEqual(result['counts'],expected['counts'])
        self.assertEqual(result['unknown_support'],expected['unknown_support'])
        self.assertGreater(rows[0]['unknown'],0)
        self.assertGreater(rows[1]['unknown'],0) # Shared diagonal inherits the unknown contributor.

    def test_triangle_trace_is_identical_across_multiple_tile_boundaries(self):
        from collections import Counter
        doc,files=fixture()
        for attachments in doc['skins'][0]['attachments'].values():
            mesh=next(iter(attachments.values()));mesh['vertices']=list(mesh['vertices'])
            mesh['vertices'][7]=600;mesh['vertices'][12]=600
        results=[]
        for tiled,sparse in [(False,False),(True,False),(True,True)]:
            rows={}
            def collect(i,values):rows.setdefault(i,Counter()).update(values)
            result=compare(Probe(doc,files,'test',tiled=tiled,sparse=sparse),'a','b',0,
                           [[.2,.3],None,[.2,.3],[.2,.3]],[[0,.1]]*4,on_triangle=collect)
            results.append((result['counts'],rows))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])


if __name__=='__main__': unittest.main()
