import unittest
from copy import deepcopy
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.mesh_depth_proxy import vertex_depths, overlap_support
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


class MeshDepthProxyTests(unittest.TestCase):
    def test_cropped_groups_preserve_known_unknown_and_ambiguous_counts(self):
        doc,files=fixture();doc['bones'][0]['length']=2
        for segments in ({'root':(.1,.2)},{'root':(-.1,-.2)},{'root':(-.1,.2)},{}):
            for intervals in (None,[[.1,.2],[-.2,-.1],None,[-.01,.01]]):
                records=[overlap_support(Probe(doc,files,'test',tiled=True,sparse=policy),
                    'a','b',0,segments,depth_intervals=intervals)
                    for policy in ('tight_triangle_boxes','tight_depth_groups','common_depth_points')]
                self.assertTrue(all(r['status']==records[0]['status'] for r in records))
                self.assertTrue(all(r['counts']==records[0]['counts'] for r in records))

    def test_optional_endpoint_caps_are_bounded_and_preserve_missing_evidence(self):
        doc,_=fixture(); doc['bones'][0]['length']=2
        mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
        mesh['vertices'][2]=-.3
        self.assertIsNone(vertex_depths(doc,mesh,{'root':(-.2,.4)})[0])
        self.assertEqual(vertex_depths(doc,mesh,{'root':(-.2,.4)},endpoint_caps=True)[0],-.2)
        mesh['vertices'][2]=2.3
        self.assertAlmostEqual(vertex_depths(doc,mesh,{'root':(-.2,.4)},endpoint_caps=True)[0],.4)
        mesh['vertices'][2]=-.6
        self.assertIsNone(vertex_depths(doc,mesh,{'root':(-.2,.4)},endpoint_caps=True)[0])
        self.assertIsNone(vertex_depths(doc,mesh,{},endpoint_caps=True)[0])

    def test_multiple_influences_use_weights_without_inventing_missing_bone_depth(self):
        doc,_=fixture(); doc['bones'][0]['length']=2
        doc['bones'].append(dict(name='second',length=2))
        mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
        mesh['vertices'][:5]=[2,0,1,0,.25,1,1,0,.75]
        self.assertAlmostEqual(vertex_depths(doc,mesh,{'root':(0,.4),'second':(.4,.8)})[0],.5)
        self.assertIsNone(vertex_depths(doc,mesh,{'root':(0,.4)})[0])

    def test_axis_interpolation_and_conservative_abstention(self):
        doc,_=fixture(); doc['bones'][0]['length']=2
        mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
        self.assertEqual(vertex_depths(doc,mesh,{'root':(-1,1)}),[-1,1,1,-1])
        self.assertEqual(vertex_depths(doc,mesh,{}),[None]*4)
        mesh['vertices'][2]=-0.1
        self.assertIsNone(vertex_depths(doc,mesh,{'root':(-1,1)})[0])
        mesh['vertices'][2]=0; mesh['vertices'][4]=.5
        self.assertIsNone(vertex_depths(doc,mesh,{'root':(-1,1)})[0])

    def test_full_opaque_overlap_uniform_and_mixed_depth(self):
        doc,files=fixture(); doc['bones'][0]['length']=2; before=deepcopy(doc)
        for segments,status in [({'root':(.1,.2)},'uniform_front_proxy'),
                                 ({'root':(-.1,-.2)},'uniform_back_proxy'),
                                 ({'root':(-.1,.2)},'requires_partition_or_more_depth'),
                                 ({},'requires_partition_or_more_depth')]:
            report=overlap_support(Probe(doc,files,'test'),'a','b',0,segments)
            self.assertEqual(report['status'],status)
            self.assertEqual(sum(report['counts'].values()),4)
            self.assertFalse(report['selected'])
        self.assertEqual(doc,before)

    def test_transparency_and_budget_are_not_false_depth_evidence(self):
        doc,files=fixture(True); doc['bones'][0]['length']=2
        report=overlap_support(Probe(doc,files,'test'),'a','b',0,{'root':(.1,.2)})
        self.assertEqual(report['status'],'no_overlap')
        doc,files=fixture(); doc['bones'][0]['length']=2
        with self.assertRaisesRegex(ValueError,'pixel_budget'):
            overlap_support(Probe(doc,files,'test',pixel_budget=10),'a','b',0,{'root':(.1,.2)})


if __name__=='__main__': unittest.main()
