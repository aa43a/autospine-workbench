import unittest
from copy import deepcopy
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.weighted_depth_interval import build
from autospine_workbench.targets.character43.mesh_depth_proxy import overlap_support
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


class WeightedIntervalTests(unittest.TestCase):
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
