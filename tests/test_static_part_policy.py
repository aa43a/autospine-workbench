from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.static_part_policy import propose, torso_evidence


class StaticPartTests(unittest.TestCase):
    def fixture(self, name='ears-l', semantic=None):
        face=dict(layer_id='face',semantic='body.face',name='face',bbox=[0,0,20,20],image_sha256='a'*64)
        part=dict(layer_id='part',semantic=semantic,name=name,bbox=[0,5,5,15],image_sha256='b'*64)
        source=SimpleNamespace(candidate={'layers':[face,part]},images={},
            assisted={'reviewed_joint_ids':['head','neck'],'draft':{'records':[
                dict(joint_id=k,status='observed',position=p) for k,p in [('head',[10,10]),('neck',[10,20])]]}},
            bindings={'bindings':[dict(layer_id='part',options=[dict(id='rigid:head',bone_ids=['head'])])]},
            draft={'records':[dict(layer_id='face',action='bind',option_id='rigid:head')]})
        before=dict(limits={},rows=[dict(layer_id='part',status='needs_review',reason_codes=['visible_face_containment'])])
        return source,before

    def raster(self,layer,_):
        x,y,a,b=layer['bbox'];return SimpleNamespace(width=a-x,pixels=bytes([0,0,0,255])*((a-x)*(b-y)))

    def run_policy(self,s,b):
        with patch('autospine_workbench.automation.static_part_policy.previous',return_value=deepcopy(b)), \
             patch('autospine_workbench.automation.static_part_policy._image',side_effect=self.raster), \
             patch('autospine_workbench.automation.head_parts_policy._image',side_effect=self.raster):
            return propose(s)['rows'][0]

    def test_named_ear_without_semantics_requires_reviewed_head_contact(self):
        s,b=self.fixture();self.assertEqual(self.run_policy(s,b)['status'],'eligible')
        s.assisted['reviewed_joint_ids']=[]
        self.assertEqual(self.run_policy(s,b),b['rows'][0])

    def test_conflicts_manual_choice_and_ambiguous_options_preserved(self):
        for change in (lambda s,b:s.candidate['layers'][1].update(semantic='accessory.object'),
                         lambda s,b:b['rows'][0].update(status='preserved'),
                         lambda s,b:s.bindings['bindings'][0]['options'].append(dict(id='rigid:root',bone_ids=['root']))):
            s,b=self.fixture();change(s,b);self.assertEqual(self.run_policy(s,b),b['rows'][0])

    def test_headwear_requires_supported_pixels_and_bounded_extent(self):
        s,b=self.fixture('headwear');self.assertEqual(self.run_policy(s,b)['status'],'eligible')
        s.candidate['layers'][1]['bbox']=[-5,0,5,10]
        self.assertIn('bound_head_support',self.run_policy(s,b)['reason_codes'])
        s.candidate['layers'][1]['bbox']=[-50,0,-40,10]
        self.assertIn('bounded_head_extent',self.run_policy(s,b)['reason_codes'])

    def test_torso_rejects_sleeve_span_and_uncovered_chest(self):
        anchors={k:dict(position=p) for k,p in [('neck',[10,5]),('chest',[10,10]),
            ('pelvis',[10,30]),('shoulder.left',[0,8]),('shoulder.right',[20,8])]}
        layer=dict(bbox=[5,5,15,25],image_sha256='a'*64)
        with patch('autospine_workbench.automation.static_part_policy._image',side_effect=self.raster):
            self.assertTrue(all(torso_evidence(layer,anchors,{})[1].values()))
            layer['bbox']=[-10,5,15,25]
            self.assertFalse(torso_evidence(layer,anchors,{})[1]['bounded_torso_extent'])
            layer['bbox']=[0,5,5,25]
            self.assertFalse(torso_evidence(layer,anchors,{})[1]['chest_on_foreground'])
