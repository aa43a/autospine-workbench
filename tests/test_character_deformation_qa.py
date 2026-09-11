from copy import deepcopy
import json
from hashlib import sha256
import unittest
from autospine_workbench.targets.character43.deformation_qa import inspect


class DeformationTests(unittest.TestCase):
    def fixture(self):
        doc={'animations':{'idle':{},'wave':{}},'skins':[{'attachments':{'arm':{'arm':{'triangles':[0,1,2]}}}}]}
        raw=json.dumps(doc).encode();frame={'time':0,'vertices':{'arm':[[0,0],[1,0],[0,1]]}}
        ref={'skeleton_sha256':sha256(raw).hexdigest(),'animations':{k:[deepcopy(frame),dict(time=1,vertices=deepcopy(frame['vertices']))] for k in doc['animations']}}
        return raw,ref

    def run_report(self,raw,ref):return inspect({'skeleton.json':raw,'numeric-reference.json':json.dumps(ref).encode()})

    def test_late_animation_inversion_not_hidden_by_idle(self):
        raw,ref=self.fixture();ref['animations']['wave'][1]['vertices']['arm'][2]=[0,-1]
        r=self.run_report(raw,ref);self.assertFalse(r['passed']);self.assertTrue(r['records'][0]['passed'])
        self.assertEqual(r['records'][1]['first_failure']['time'],1)
        self.assertEqual(r['records'][1]['inversion_samples'],1)

    def test_rigid_translation_passes_but_stretch_fails(self):
        raw,ref=self.fixture();ref['animations']['wave'][1]['vertices']['arm']=[[10,10],[11,10],[10,11]]
        self.assertTrue(self.run_report(raw,ref)['passed'])
        ref['animations']['wave'][1]['vertices']['arm'][1]=[13,10]
        self.assertFalse(self.run_report(raw,ref)['passed'])

    def test_mismatched_inventory_nonfinite_and_source_rejected(self):
        for change in [lambda r:r.update(skeleton_sha256='0'*64),lambda r:r['animations'].pop('wave'),
                       lambda r:r['animations']['idle'][1]['vertices']['arm'][0].__setitem__(0,float('nan'))]:
            raw,ref=self.fixture();change(ref)
            with self.assertRaises(ValueError):self.run_report(raw,ref)
