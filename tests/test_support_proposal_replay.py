from copy import deepcopy
from hashlib import sha256
import unittest
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.support_proposal_replay import replay,without_generated_deform


class ProposalTests(unittest.TestCase):
    def test_exact_replay_and_changed_source_rejection(self):
        names=('thigh_l','calf_l','thigh_r','calf_r')
        tracks={n:{'rotate':[dict(time=0,value=10),dict(time=1,value=20)]} for n in names}
        tracks['root']={'translate':[dict(time=0,x=0,y=0),dict(time=1,x=3,y=4)]}
        doc={'bones':[],'animations':{'a':{'bones':tracks}}};before=deepcopy(doc)
        contact=dict(selected=False,input_skeleton_sha256=sha256(canonical_bytes(doc)).hexdigest(),
            phase_attempt=dict(status='candidate',profile='causal-joint-support-timeline-v1',
                rows=[dict(time=t,root_shift=[2,1],angles={n:5 for n in names}) for t in (0,1)]))
        result=replay(doc,'a',contact)
        self.assertEqual(doc,before)
        self.assertEqual(result['animations']['a']['bones']['root']['translate'][-1],dict(time=1,x=5,y=5))
        self.assertEqual(result['animations']['a']['bones']['calf_l']['rotate'][-1]['value'],25)
        doc['bones'].append({'name':'changed'})
        with self.assertRaisesRegex(ValueError,'base_changed'):replay(doc,'a',contact)

    def test_does_not_remove_unowned_deform(self):
        doc={'animations':{'a':{'bones':{},'attachments':{'default':{'user':{'user':{'deform':[]}}}}}}}
        with self.assertRaisesRegex(ValueError,'inventory_mismatch'):
            without_generated_deform(doc,'a',{'records':[]})
        result=without_generated_deform(doc,'a',{'records':[{'slot':'user'}]})
        self.assertNotIn('attachments',result['animations']['a'])
        self.assertIn('attachments',doc['animations']['a'])
