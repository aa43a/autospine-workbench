from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from autospine_workbench.automation.eye_neighborhood_policy import propose,evidence


class EyeNeighborhoodTests(unittest.TestCase):
    def source(self):
        def layer(key,name,box,semantic=None):
            return dict(layer_id=key,name=name,bbox=box,semantic=semantic,image_sha256='a'*64)
        layers=[layer('face','face',[10,10,120,120],'body.face'),
                layer('eye-l','eyewhite-l',[30,50,50,70]),
                layer('eye-r','eyewhite-r',[80,50,100,70]),
                layer('lash','eyelash-l',[25,48,53,60])]
        source=SimpleNamespace(candidate=dict(layers=layers),images={},
            draft=dict(records=[dict(layer_id=l['layer_id'],action='bind' if i<3 else 'pending',
                                    option_id='rigid:head' if i<3 else None,notes='') for i,l in enumerate(layers)]),
            assisted=dict(reviewed_joint_ids=['head','neck'],draft=dict(records=[dict(joint_id=k,status='observed') for k in ('head','neck')])),
            bindings=dict(bindings=[dict(layer_id='lash',options=[dict(id='rigid:head',bone_ids=['head'])])]))
        previous=dict(limits={},rows=[dict(layer_id='lash',status='needs_review',option_id=None,
                                            reason_codes=['visible_face_containment'],checks={},evidence={})])
        return source,previous

    def raster(self,layer,images):
        x,y,r,b=layer['bbox'];w=r-x;h=b-y
        raw=bytearray([0,0,0,255]*(w*h))
        if layer['layer_id']=='face':
            # A cut-out edge near the lash does not erase the eye reference.
            for px in range(25,35):
                for py in range(48,50):
                    if x<=px<r and y<=py<b:raw[((py-y)*w+px-x)*4+3]=0
        return SimpleNamespace(width=w,height=h,pixels=bytes(raw))

    def run_policy(self,source,previous):
        with patch('autospine_workbench.automation.eye_neighborhood_policy.previous',return_value=deepcopy(previous)), \
             patch('autospine_workbench.automation.eye_neighborhood_policy._image',side_effect=self.raster):
            return propose(source)

    def test_local_eye_support_complements_face_edge_without_changing_sources(self):
        source,prior=self.source();before=deepcopy(vars(source))
        row=self.run_policy(source,prior)['rows'][0]
        self.assertEqual(row['status'],'eligible')
        self.assertTrue(all(row['checks'].values()))
        self.assertEqual(row['option_id'],'rigid:head')
        self.assertEqual(vars(source),before)

    def test_far_cross_eye_and_detached_content_remain_exceptions(self):
        for box,reason in [([20,45,70,60],'inside_eye_neighborhood'),
                           ([25,38,53,43],'eyelash_eye_contact'),
                           ([80,48,100,60],'inside_eye_neighborhood')]:
            source,prior=self.source();source.candidate['layers'][-1]['bbox']=box
            row=self.run_policy(source,prior)['rows'][0]
            self.assertEqual(row['status'],'needs_review');self.assertIn(reason,row['reason_codes'])

    def test_reviewed_references_unique_options_and_exact_scope_required(self):
        changes=[lambda s:s.draft['records'][1].update(action='pending'),
                 lambda s:s.assisted.update(reviewed_joint_ids=['head']),
                 lambda s:s.bindings['bindings'][0]['options'].append(dict(id='rigid:chest',bone_ids=['chest'])),
                 lambda s:s.candidate['layers'][-1].update(semantic='body.hand'),
                 lambda s:s.candidate['layers'][-1].update(name='headwear')]
        for change in changes:
            source,prior=self.source();change(source)
            self.assertEqual(self.run_policy(source,prior)['rows'],prior['rows'])

    def test_prior_decisions_notes_and_other_failures_are_not_overridden(self):
        for status,reasons in [('preserved',['existing_review_preserved']),
                               ('needs_review',['visible_face_containment','small_head_feature'])]:
            source,prior=self.source();prior['rows'][0].update(status=status,reason_codes=reasons)
            self.assertEqual(self.run_policy(source,prior)['rows'],prior['rows'])

    def test_scale_translation_and_eye_separation(self):
        source,_=self.source();face,eye,other,lash=source.candidate['layers']
        with patch('autospine_workbench.automation.eye_neighborhood_policy._image',side_effect=self.raster):
            _,before=evidence(lash,eye,other,face,{})
            for layer in (face,eye,other,lash):layer['bbox']=[v*2+100 for v in layer['bbox']]
            _,after=evidence(lash,eye,other,face,{})
            self.assertEqual(before,after)
            other['bbox']=deepcopy(eye['bbox'])
            _,checks=evidence(lash,eye,other,face,{})
            self.assertFalse(checks['distinct_eye_neighborhood'])
