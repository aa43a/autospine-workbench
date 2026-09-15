from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.head_parts_policy import propose, evidence


class HeadPartsTests(unittest.TestCase):
    def fixture(self):
        face=dict(layer_id='face',name='face',semantic='body.face',bbox=[20,20,60,60],image_sha256='a'*64)
        hair=dict(layer_id='hair',name='front hair',semantic='hair.front',bbox=[5,5,65,65],image_sha256='b'*64)
        source=SimpleNamespace(candidate=dict(layers=[face,hair]),images={},
            draft=dict(records=[dict(layer_id='face',action='bind',option_id='rigid:head')]),
            assisted=dict(reviewed_joint_ids=['head','neck'],draft=dict(records=[dict(joint_id=k,status='observed') for k in ('head','neck')])),
            bindings=dict(bindings=[dict(layer_id='hair',options=[dict(id='rigid:head',bone_ids=['head'])])]))
        before=dict(limits={},rows=[dict(layer_id='hair',status='needs_review',reason_codes=['policy_capability_unsupported'])])
        return source,before

    def raster(self,layer,images):
        x,y,r,b=layer['bbox'];return SimpleNamespace(width=r-x,height=b-y,pixels=bytes([0,0,0,255])*(r-x)*(b-y))

    def run_policy(self,source,before):
        with patch('autospine_workbench.automation.head_parts_policy.previous',return_value=deepcopy(before)),patch('autospine_workbench.automation.head_parts_policy._image',side_effect=self.raster):
            return propose(source)

    def test_bounded_hair_is_static_candidate(self):
        source,before=self.fixture();row=self.run_policy(source,before)['rows'][0]
        self.assertEqual(row['status'],'eligible');self.assertEqual(row['option_id'],'rigid:head')
        self.assertEqual(row['evidence']['mode'],'static_head_follow')

    def test_long_detached_or_conflicting_parts_are_not_adopted(self):
        for mutation in (lambda s:s.candidate['layers'][1].update(bbox=[5,5,65,100]),
            lambda s:s.candidate['layers'][1].update(bbox=[0,0,10,10]),
            lambda s:s.candidate['layers'][1].update(semantic='wear.top'),
            lambda s:s.bindings['bindings'][0]['options'].append(dict(id='rigid:chest',bone_ids=['chest'])),
            lambda s:s.assisted.update(reviewed_joint_ids=['head']),
            lambda s:s.draft['records'][0].update(action='pending')):
            source,before=self.fixture();mutation(source)
            self.assertNotEqual(self.run_policy(source,before)['rows'][0]['status'],'eligible')

    def test_user_record_and_exception_note_preserved(self):
        source,before=self.fixture();before['rows'][0].update(status='preserved',reason_codes=['existing_review_preserved'])
        self.assertEqual(self.run_policy(source,before)['rows'][0],before['rows'][0])

    def test_geometry_is_translation_and_scale_invariant(self):
        source,_=self.fixture();face,hair=source.candidate['layers']
        with patch('autospine_workbench.automation.head_parts_policy._image',side_effect=self.raster):
            _,original=evidence(hair,face,{})
            for layer in (face,hair):layer['bbox']=[v*2+100 for v in layer['bbox']]
            _,changed=evidence(hair,face,{})
        self.assertEqual(original,changed)
