from copy import deepcopy
import unittest
from autospine_workbench.targets.spine43.merge_limb_tracks import merge


class MergeLimbTests(unittest.TestCase):
    def fixture(self,name,bone):
        return dict(bones=[{'name':'root'}],slots=[{'name':name}],skins=[{'attachments':{name:{name:{'type':'mesh','vertices':[]}}}}],
                    animations={'test':{'bones':{bone:{'rotate':[{'time':0,'value':0},{'time':2,'value':0}]}},'attachments':{'default':{name:{name:{'deform':[]}}}}}})

    def test_disjoint_union_preserves_inputs_and_tracks(self):
        a,b=self.fixture('leg','knee'),self.fixture('arm','elbow');original=deepcopy(a)
        result=merge(a,b,['arm'])
        self.assertEqual(a,original)
        self.assertEqual(result['animations']['test']['bones']['knee'],a['animations']['test']['bones']['knee'])
        self.assertEqual(set(result['skins'][0]['attachments']),{'arm','leg'})

    def test_conflicts_and_wrong_sources_fail(self):
        a,b=self.fixture('leg','joint'),self.fixture('arm','joint');b['animations']['test']['bones']['joint']['rotate'][0]['value']=5
        with self.assertRaisesRegex(ValueError,'track_conflict'):merge(a,b,['arm'])
        b=self.fixture('arm','elbow');b['bones']=[{'name':'other'}]
        with self.assertRaisesRegex(ValueError,'skeleton'):merge(a,b,['arm'])
        with self.assertRaisesRegex(ValueError,'selection'):merge(a,a,['leg','leg'])
        with self.assertRaisesRegex(ValueError,'attachment'):merge(a,a,['leg'])

    def test_different_clip_duration_rejected(self):
        a,b=self.fixture('leg','knee'),self.fixture('arm','elbow')
        b['animations']['test']['bones']['elbow']['rotate'][-1]['time']=3
        with self.assertRaisesRegex(ValueError,'duration'):merge(a,b,['arm'])
