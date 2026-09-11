from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.head_anchor_policy import propose,anchor_evidence


class HeadAnchorTests(unittest.TestCase):
    def fixture(self):
        face=dict(layer_id='face',semantic='body.face',name='face',bbox=[0,0,20,20],image_sha256='a'*64)
        neck=dict(layer_id='neck',semantic='body.neck',name='neck',bbox=[5,15,15,40],image_sha256='b'*64)
        source=SimpleNamespace(candidate={'layers':[face,neck]},images={},
            assisted={'reviewed_joint_ids':['head','neck'],'draft':{'records':[dict(joint_id=k,status='observed',position=p) for k,p in [('head',[10,10]),('neck',[10,30])]]}},
            bindings={'bindings':[dict(layer_id=k,options=[{'id':'rigid:'+v}]) for k,v in [('face','head'),('neck','neck')]]})
        before={'limits':{},'rows':[dict(layer_id=k,status='needs_review',reason_codes=['policy_capability_unsupported']) for k in ['face','neck']]}
        return source,before

    def raster(self,layer,images):
        b=layer['bbox'];return SimpleNamespace(width=b[2]-b[0],height=b[3]-b[1],pixels=bytes([0,0,0,255])*((b[2]-b[0])*(b[3]-b[1])))

    def run_policy(self,source,before):
        with patch('autospine_workbench.automation.head_anchor_policy.previous',return_value=deepcopy(before)),patch('autospine_workbench.automation.head_anchor_policy._image',side_effect=self.raster):return propose(source)

    def test_reviewed_anchors_seed_head_but_preserve_existing_selection(self):
        s,b=self.fixture();r=self.run_policy(s,b)
        self.assertTrue(all(x['status']=='eligible' for x in r['rows']))
        b['rows'][0].update(status='preserved',reason_codes=['existing_review_preserved'])
        self.assertEqual(self.run_policy(s,b)['rows'][0],b['rows'][0])

    def test_unreviewed_anchor_duplicate_face_and_missing_overlap_not_adopted(self):
        for mutation in [lambda s:s.assisted.update(reviewed_joint_ids=['head']),
                         lambda s:s.candidate['layers'].append(deepcopy(s.candidate['layers'][0])),
                         lambda s:s.candidate['layers'][1].update(bbox=[5,25,15,40])]:
            s,b=self.fixture();mutation(s)
            self.assertFalse(any(x['status']=='eligible' for x in self.run_policy(s,b)['rows']))

    def test_off_image_and_oversized_neck_fail(self):
        for mutation in [lambda s:s.assisted['draft']['records'][0].update(position=[100,10]),
                         lambda s:s.candidate['layers'][1].update(bbox=[-20,15,40,40])]:
            s,b=self.fixture();mutation(s)
            self.assertFalse(any(x['status']=='eligible' for x in self.run_policy(s,b)['rows']))
