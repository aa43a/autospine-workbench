import unittest
from copy import deepcopy
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.weighted_depth_interval import build
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


class WeightedIntervalTests(unittest.TestCase):
    def test_leg_envelope_is_explicit_and_rejects_foot_or_broken_chain(self):
        doc,_=fixture()
        doc['bones']=[dict(name='thigh_r',length=1),dict(name='calf_r',parent='thigh_r',length=1)]
        mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
        mesh['vertices'][:5]=[2,0,.5,0,.9,1,-2,0,.1]
        segments={'thigh_r':(0,.2),'calf_r':(.2,.4)}
        self.assertIsNone(build(doc,mesh,segments)['intervals'][0])
        result=build(doc,mesh,segments,chain_kind='leg')
        self.assertAlmostEqual(result['intervals'][0][0],.09)
        self.assertAlmostEqual(result['intervals'][0][1],.13)
        doc['bones'][1]['parent']='root'
        self.assertIsNone(build(doc,mesh,segments,chain_kind='leg')['intervals'][0])
        doc['bones'][1]['name']='foot_r'
        self.assertIsNone(build(doc,mesh,segments,chain_kind='leg')['intervals'][0])

    def test_all_weights_contribute_and_unknown_requires_known_same_chain_support(self):
        doc,_=fixture()
        doc['bones']=[dict(name='upperarm_r',length=1),dict(name='forearm_r',parent='upperarm_r',length=1),
                      dict(name='hand_r',parent='forearm_r',length=1)]
        mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
        mesh['vertices'][:5]=[2,0,2,0,.1,1,.5,0,.9]
        segments={'upperarm_r':(0,.2),'forearm_r':(.2,.4),'hand_r':(.4,.6)}
        before=deepcopy(mesh); report=build(doc,mesh,segments)
        self.assertAlmostEqual(report['intervals'][0][0],.27)
        self.assertAlmostEqual(report['intervals'][0][1],.33)
        self.assertIsNone(report['intervals'][1])
        self.assertEqual(mesh,before)
        doc['bones'][2]['parent']='upperarm_r'
        self.assertIsNone(build(doc,mesh,segments)['intervals'][0])

    def test_whole_interval_not_midpoint_must_clear_front_margin(self):
        doc,files=fixture(); doc['bones'][0]['length']=2
        good=overlap_support(Probe(doc,files,'test'),'a','b',0,{'root':(.1,.2)},depth_intervals=[[.03,.4]]*4)
        uncertain=overlap_support(Probe(doc,files,'test'),'a','b',0,{'root':(.1,.2)},depth_intervals=[[-.01,.4]]*4)
        self.assertEqual(good['status'],'uniform_front_proxy')
        self.assertEqual(uncertain['status'],'requires_partition_or_more_depth')
        with self.assertRaisesRegex(ValueError,'intervals_invalid'):
            overlap_support(Probe(doc,files,'test'),'a','b',0,{'root':(.1,.2)},depth_intervals=[[.2,.1]]*4)


if __name__=='__main__': unittest.main()
