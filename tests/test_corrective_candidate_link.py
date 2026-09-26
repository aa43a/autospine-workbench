from copy import deepcopy
from hashlib import sha256
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes as raw
from autospine_workbench.resolved_project import canonical_sha256
from m4_register_corrective_candidate import receipt_for


class CorrectiveLinkTests(unittest.TestCase):
    def setUp(self):
        self.request=dict(character_sha256='a'*64,motion_identity={'clip':'b'*64})
        self.origin=dict(request_sha256=canonical_sha256(self.request),
            character_sha256=self.request['character_sha256'],motion_identity=self.request['motion_identity'],
            candidate_bundle_sha256='c'*64)
        self.doc={'animations':{'external-motion':{'bones':{},'attachments':{'default':{
            'leg':{'leg':{'deform':[{'time':0,'vertices':[0,0]},{'time':1,'vertices':[0,0]}]}}}}}}}
        self.old={'skeleton.json':raw(self.doc),'character-manifest.json':b'{}','images/a.png':b'pixels',
            'numeric-reference.json':raw({'animations':{'external-motion':[{'time':0},{'time':1}]}})}
        self.files=deepcopy(self.old)
        self.files['numeric-reference.json']=raw({'animations':{'external-motion':[{'time':t} for t in (0,.5,1)]}})
        self.proof={'skeleton_sha256':sha256(self.files['skeleton.json']).hexdigest(),'selected_slots':['leg']}
        self.files['corrective-provenance.json']=raw(self.proof)

    def check(self):
        return receipt_for(self.request,self.origin,self.old,{},self.files,{'results':[{}, {}, {}]})

    def test_complete_legacy_capture_and_input_preservation(self):
        before=deepcopy(self.files);r=self.check()
        self.assertFalse(r['selected']);self.assertIn('visual',r['remaining_checks'])
        self.assertEqual(r['sampled_frames'],3);self.assertEqual(before,self.files)

    def test_missing_midpoint_or_partial_capture_refused(self):
        self.files['numeric-reference.json']=self.old['numeric-reference.json']
        with self.assertRaisesRegex(ValueError,'sampling_incomplete'):self.check()
        self.proof['partial_time_batch']=True
        self.files['corrective-provenance.json']=raw(self.proof)
        with self.assertRaisesRegex(ValueError,'incomplete_proof'):self.check()

    def test_bone_changes_and_texture_changes_refused(self):
        self.files['images/a.png']=b'changed'
        with self.assertRaisesRegex(ValueError,'texture_changed'):self.check()
        self.files['images/a.png']=b'pixels'
        self.doc['animations']['external-motion']['bones']={'root':{'rotate':[{'time':0,'angle':10}]}}
        self.files['skeleton.json']=raw(self.doc)
        self.proof['skeleton_sha256']=sha256(self.files['skeleton.json']).hexdigest()
        self.files['corrective-provenance.json']=raw(self.proof)
        with self.assertRaisesRegex(ValueError,'unrelated_change'):self.check()

    def test_request_change_refused(self):
        self.request['character_sha256']='d'*64
        with self.assertRaisesRegex(ValueError,'source_identity'):self.check()
