import json
import unittest
from unittest.mock import patch
from test_repair_feasibility import evidence
from m4_hand_transition_probe import solve


class TransitionTests(unittest.TestCase):
    def files(self):
        files=evidence();doc=json.loads(files['skeleton.json'])
        doc['animations']['external-motion']=doc['animations'].pop('walk')
        files['skeleton.json']=json.dumps(doc).encode()
        reference=json.loads(files['numeric-reference.json'])
        reference['animations']['external-motion']=reference['animations'].pop('walk')
        files['numeric-reference.json']=json.dumps(reference).encode()
        return files

    def test_fixed_failure_never_calls_optimizer(self):
        files=self.files()
        # The attachment uses one bone; provide a positive chain length to match the policy.
        doc=json.loads(files['skeleton.json'])
        doc['bones'][0]['parent']='root'
        doc['bones'].insert(0,dict(name='root',x=0,y=0,rotation=0))
        mesh=doc['skins'][0]['attachments']['mesh']['mesh']
        # Two fixed bones form the mesh: no mixed vertex is movable.
        mesh['vertices']=[1,0,0,0,1,1,1,1,0,1,1,1,0,1,1]
        doc['bones'][1]['x']=10
        files['skeleton.json']=json.dumps(doc).encode()
        with patch('m4_hand_transition_probe.refine') as optimizer:
            _,report=solve(files,'mesh')
        optimizer.assert_not_called()
        self.assertTrue(any(r['solver']['status']=='fixed_vertex_counterexample' for r in report['rows']))

    def test_existing_deform_not_overwritten(self):
        files=self.files();doc=json.loads(files['skeleton.json'])
        doc['animations']['external-motion']['attachments']={'default':{'mesh':{'mesh':{'deform':[dict(time=0,vertices=[])]}}}}
        files['skeleton.json']=json.dumps(doc).encode()
        with self.assertRaisesRegex(ValueError,'explicit_rebase'):solve(files,'mesh')
