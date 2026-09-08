import unittest
from autospine_workbench.targets.spine43.alpha_curves import trace,anchors
from autospine_workbench.targets.spine43.alpha_curve_validation import validate


class AlphaCurvesTests(unittest.TestCase):
    def test_rectangle_perimeter_once(self):
        c=trace([[1,1],[1,1]])
        self.assertEqual(len(c),1);self.assertTrue(c[0]['closed'])
        self.assertEqual(len(c[0]['edge_pixels']),8)
        self.assertEqual(len(set(zip(map(tuple,c[0]['points']),map(tuple,c[0]['points'][1:])))),8)

    def test_hole_opposite_winding(self):
        curves=trace([[1,1,1],[1,0,1],[1,1,1]])
        area=lambda c:sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(c['points'],c['points'][1:]))
        self.assertEqual(sorted(area(c) for c in curves),[-2,18])

    def test_diagonal_contact_is_ambiguous(self):
        curves=trace([[1,0],[0,1]])
        self.assertEqual(sum(len(c['edge_pixels']) for c in curves),8)
        self.assertTrue(all(c['status']=='ambiguous_corner' for c in curves))

    def test_empty_and_shape(self):
        self.assertEqual(trace([]),[])
        with self.assertRaisesRegex(ValueError,'curve_mask_shape'):trace([[1],[]])

    def test_all_three_by_three_masks_preserve_exposed_edges(self):
        for bits in range(512):
            mask=[[bool(bits & (1<<(y*3+x))) for x in range(3)] for y in range(3)]
            count=sum(sum(row) for row in mask)
            shared=sum(mask[y][x] and mask[y][x+1] for y in range(3) for x in range(2))
            shared+=sum(mask[y][x] and mask[y+1][x] for y in range(2) for x in range(3))
            curves=trace(mask)
            edges=[(tuple(a),tuple(b)) for c in curves for a,b in zip(c['points'],c['points'][1:])]
            self.assertEqual(len(edges),4*count-2*shared,bits)
            self.assertEqual(len(edges),len(set(edges)),bits)

    def test_anchor_embedding_and_corner_ties(self):
        curves=trace([[1,1,1],[1,1,1],[1,1,1]])
        att={'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]}
        result=anchors(curves,[{'pixel_xy':[1,0]},{'pixel_xy':[0,0]}],[0,1],att,[3,3])
        self.assertEqual(result[0]['status'],'candidate_anchor')
        self.assertEqual(result[0]['options'][0]['pixel_xy'],[1.5,0.])
        self.assertAlmostEqual(sum(result[0]['options'][0]['embedding']['barycentric']),1)
        self.assertEqual(result[1]['status'],'ambiguous_projection')
        self.assertEqual(len(result[1]['options']),2)

    def test_mesh_outside_is_not_clamped(self):
        att={'uvs':[.2,.2,.8,.2,.5,.8],'triangles':[0,1,2]}
        r=anchors(trace([[1,1,1],[1,1,1]]),[{'pixel_xy':[1,0]}],[0],att,[3,2])
        self.assertEqual(r[0]['status'],'unmapped_mesh')

    def test_validation_rejects_bad_reference_and_nonfinite_weights(self):
        curves=trace([[1,1,1],[1,1,1]])
        att={'uvs':[0,0,1,0,1,1,0,1],'triangles':[0,1,2,0,2,3]}
        aa=anchors(curves,[{'pixel_xy':[1,0]}],[0],att,[3,2])
        report={'schema':'autospine.alpha-curve-anchors/v1','authority':'none','production_authorized':False,
                'status':'needs_review','curves':{'attachments':[{'attachment':'shoe','curves':curves,
                'anchors':aa,'boundary_edges':10}]}}
        self.assertIs(validate(report),report)
        option=aa[0]['options'][0];original=option['curve'];option['curve']=99
        with self.assertRaisesRegex(ValueError,'curve_reference'):validate(report)
        option['curve']=original;option['embedding']['barycentric'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'curve_embedding'):validate(report)
