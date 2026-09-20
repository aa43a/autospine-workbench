from copy import deepcopy
from types import SimpleNamespace
import unittest
import numpy as np
from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.hand_mesh_axis import infer
from autospine_workbench.targets.character43.mesh_depth_proxy import vertex_depths
from autospine_workbench.targets.character43.hand_depth_observation import observe


class HandAxisTests(unittest.TestCase):
    def test_opaque_dominant_support_is_distinct_from_display_length(self):
        doc,_=fixture(); doc['bones'][0].update(name='hand_r',length=.1)
        mesh=deepcopy(doc['skins'][0]['attachments']['a']['a'])
        for i,x in enumerate([.2,.7,1.2,2.]): mesh['vertices'][5*i+2]=x
        original=deepcopy(doc)
        report=infer(doc,mesh,np.full((2,2),255.))
        self.assertEqual(report['axes']['hand_r']['length'],2)
        values=vertex_depths(doc,mesh,{'hand_r':(0,1)},axis_lengths={'hand_r':2})
        self.assertEqual(values,[.1,.35,.6,1.])
        self.assertEqual(doc,original)
        self.assertEqual(infer(doc,mesh,np.zeros((2,2)))['axes'],{})
        mesh['vertices'][4]=.1; mesh['vertices'][9]=.1
        self.assertEqual(infer(doc,mesh,np.full((2,2),255.))['axes'],{})

    def test_full_source_hand_requires_complete_direct_chain_and_end_site(self):
        names=['LeftHand','LeftHandMiddle1','LeftHandMiddle2','LeftHandMiddle3']
        depths=dict(zip(names,[0,.1,.2,.3])); depths[names[-1],'end_site']=.4
        sampler=SimpleNamespace(mapping={'map_id':'mixamo-declared-body-v1'},
            roles={'humanoid.arm.lower.left':{'aim':{'joint_name':'LeftHand'}}},
            indices={n:i for i,n in enumerate(names)},
            bvh=SimpleNamespace(joints=[SimpleNamespace(parent_index=i-1) for i in range(4)]),
            joint_depths=lambda *a,**kw:depths)
        self.assertEqual(observe(sampler,0,full_hand=True)['segments'],{'hand_l':(0,.4)})
        del depths[names[-1],'end_site']
        self.assertEqual(observe(sampler,0,full_hand=True)['segments'],{})
        self.assertEqual(observe(sampler,0)['segments'],{'hand_l':(0,.1)})


if __name__=='__main__': unittest.main()
