from copy import deepcopy
import unittest
from test_character_affine_repair import fixture
from m4_kimodo_hand_candidate import candidate


class CandidateTests(unittest.TestCase):
    def test_wrist_and_upstream_preserved_stale_hand_deform_removed(self):
        doc=fixture();doc['bones'][0]['name']='forearm_l'
        doc['bones'][1].update(name='hand_l',parent='forearm_l')
        right=deepcopy(doc['bones'][1]);right.update(name='hand_r',parent='forearm_l',y=5)
        doc['bones'].append(right)
        doc['animations']={'external-motion':{'bones':{'forearm_l':{'scale':[
            dict(time=0,x=1,y=1),dict(time=1,x=.4,y=1)]}},
            'attachments':{'default':{'mesh':{'mesh':{'deform':[dict(time=0,vertices=[0]*10)]}}}}}}
        mesh=doc['skins'][0]['attachments']['mesh']['mesh'];mesh['uvs']=[0,0,1,0,0,1]
        doc['slots']=[dict(name='mesh',bone='forearm_l',attachment='mesh')]
        original=deepcopy(doc)
        observed=dict(times=[0,1],vectors={f'humanoid.arm.hand.{s}':[(1,0,0),(1,-1,1)] for s in ('left','right')})
        result,report=candidate(doc,observed)
        self.assertEqual(doc,original)
        self.assertEqual(result['animations']['external-motion']['bones']['forearm_l'],doc['animations']['external-motion']['bones']['forearm_l'])
        self.assertEqual(report['maximum_wrist_displacement_px'],0)
        self.assertNotIn('deform',result['animations']['external-motion']['attachments']['default']['mesh']['mesh'])
        self.assertEqual(result['skins'],doc['skins'])
