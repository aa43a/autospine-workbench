import unittest
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.cloth_depth_plane import fit
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


class ClothPlaneTests(unittest.TestCase):
    def test_plane_interpolates_source_anchors_and_translation(self):
        points = dict(upperarm_l=[-2,3],upperarm_r=[2,3],pelvis=[0,0])
        depths = dict(upperarm_l=-.2,upperarm_r=.2,pelvis=.3)
        result = fit(points,depths)
        for name,p in points.items():
            a,b,c = result['coefficients']
            self.assertAlmostEqual(a*p[0]+b*p[1]+c,depths[name])
        moved = fit({n:[p[0]+100,p[1]-20] for n,p in points.items()},depths)
        self.assertAlmostEqual(moved['coefficients'][0],a)
        self.assertAlmostEqual(moved['coefficients'][1],b)
        self.assertFalse(result['selected'])

    def test_missing_or_edge_on_anchors_abstain(self):
        depths = dict(upperarm_l=0,upperarm_r=0,pelvis=0)
        with self.assertRaisesRegex(ValueError,'anchors_missing'):
            fit({},depths)
        with self.assertRaisesRegex(ValueError,'anchors_degenerate'):
            fit(dict(upperarm_l=[0,2],upperarm_r=[0,3],pelvis=[0,0]),depths)

    def test_plane_changes_relative_depth_without_changing_default(self):
        doc,files = fixture(); doc['bones'][0]['length']=2
        segments={'root':(.1,.1)}
        before=overlap_support(Probe(doc,files,'test'),'a','b',0,segments)
        after=overlap_support(Probe(doc,files,'test'),'a','b',0,segments,reference_plane=[0,0,.2])
        self.assertEqual(before['status'],'uniform_front_proxy')
        self.assertEqual(after['status'],'uniform_back_proxy')
        tilted=overlap_support(Probe(doc,files,'test'),'a','b',0,segments,reference_plane=[.1,0,0])
        self.assertEqual(tilted['status'],'requires_partition_or_more_depth')
        with self.assertRaisesRegex(ValueError,'plane_invalid'):
            overlap_support(Probe(doc,files,'test'),'a','b',0,segments,reference_plane=[float('nan'),0,0])


if __name__ == '__main__': unittest.main()
