"""Alpha boundary embedding, deterministic correspondence, and local bounds."""
from io import BytesIO
import math
import unittest
from PIL import Image
from autospine_workbench.targets.spine43.alpha_seam import embed,position,boundary,nearest_pairs
from autospine_workbench.targets.spine43.alpha_seam_bake import solve,bake
from tests.test_seam_translation import fixture


class AlphaSeamTests(unittest.TestCase):
    def test_barycentric_reconstructs_interior_and_affine_motion(self):
        sample=embed((.25,.25),[(0,0),(1,0),(0,1)],[[0,1,2]])
        self.assertEqual(position(sample,[[10,20],[14,20],[10,24]]),[11,21])
        self.assertIsNone(embed((1,1),[(0,0),(1,0),(0,1)],[[0,1,2]]))

    def test_pixel_boundary_and_unmapped_coverage(self):
        stream=BytesIO();Image.new('RGBA',(4,4),(255,255,255,255)).save(stream,format='PNG')
        a={'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]}
        result=boundary(a,stream.getvalue())
        self.assertEqual(len(result['samples']),12);self.assertEqual(result['unmapped_pixels'],0)
        a['triangles']=[0,1,2]
        self.assertGreater(boundary(a,stream.getvalue())['unmapped_pixels'],0)

    def test_nearest_tie_and_distance_gate(self):
        pairs=nearest_pairs([[0,0],[20,20]],[[-1,0],[1,0]])
        self.assertEqual(pairs,[{'driver_sample':0,'follower_sample':0,'setup_distance_px':1.}])

    def test_projection_budget_and_fixed_outside_support(self):
        vertices=[[0,0],[1,0],[0,1],[200,200]]
        anchors=[{'triangle':[0,1,2],'barycentric':[1.,0.,0.]}]
        result=solve(vertices,anchors,[[100,0]],[[0,1,2]])
        self.assertEqual(result[3],[0.,0.]);self.assertTrue(all(math.hypot(*p)<=12+1e-9 for p in result))
        self.assertEqual(result,solve(vertices,anchors,[[100,0]],[[0,1,2]]))

    def test_transparent_input_noop_and_purity(self):
        source,files=fixture(alpha=0)
        import copy
        before=copy.deepcopy(source);_,report=bake(source,files)
        self.assertEqual(source,before);self.assertEqual(report['status'],'candidate_noop')
        self.assertEqual(report['after']['relations'],[])

    def test_local_bake_preserves_setup_and_loop(self):
        source,files=fixture();points=[(0,0),(4,0),(4,4),(0,4)]
        attachments=source['skins'][0]['attachments']
        attachments['leg']['leg']={'vertices':[v for x,y in points for v in (2,0,x,y,.5,1,x,y,.5)],'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]}
        attachments['shoe']['shoe']={'vertices':[v for x,y in points for v in (1,1,x,y,1)],'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]}
        animation=source['animations']['continuous-corrective-inspection']
        animation['attachments']['default']['leg']['leg']['deform']=[{'time':t,'vertices':[d,0.]*8} for t,d in ((0,0),(1,2),(2,0))]
        from autospine_workbench.targets.spine43.continuous_pose import world
        doc,report=bake(source,files)
        self.assertEqual(len(report['constraints']),1)
        self.assertGreater(report['constraints'][0]['max_displacement_px'],0)
        self.assertEqual(world(doc,0),world(source,0));self.assertEqual(world(doc,0),world(doc,2))
        self.assertTrue(all(r['passed'] for r in report['geometry']['regions'].values()))
