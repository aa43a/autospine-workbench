import unittest
from autospine_workbench.targets.character43.depth_region_constraints import build


class RegionConstraintTests(unittest.TestCase):
    def test_both_partitioned_endpoints_expand_without_stale_slot_names(self):
        regions=[dict(source_slot=a,slot=b,triangles=[i]) for a,b,i in [('a','a1',0),('b','b1',0),('b','b2',1)]]
        a=dict(time=.25,source_tick=300000,labels=[1],observed_states=['F'])
        b=dict(time=.25,source_tick=300000,labels=[0,0],observed_states=['B','U'])
        pairs=build(dict(regions=regions),{'a':{'b':[a]},'b':{'a':[b]}})
        self.assertEqual(len(pairs),4)
        self.assertEqual({p['torso_slot'] for p in pairs},{'a1','b1','b2'})
        self.assertTrue(all(p['samples'][0]['current_front_slot']=='a1' for p in pairs))
        self.assertTrue(pairs[-1]['samples'][0]['ambiguous'])
        with self.assertRaisesRegex(ValueError,'pair_limit'):build(dict(regions=regions),{'a':{'b':[a]},'b':{'a':[b]}},pair_limit=3)
        b['observed_states']=['B','N']
        pruned=build(dict(regions=regions),{'a':{'b':[a]},'b':{'a':[b]}})
        self.assertEqual(len(pruned),2)
        self.assertTrue(all(p['arm_slot']!='b2' and p['torso_slot']!='b2' for p in pruned))

    def test_unsplit_body_and_mixed_signatures(self):
        p=dict(regions=[dict(source_slot='a',slot='a1',triangles=[0,1])])
        f=dict(time=0,source_tick=0,labels=[0,0],observed_states=['B','B'])
        self.assertEqual(build(p,{'a':{'body':[f]}})[0]['samples'][0]['current_front_slot'],'body')
        f['labels']=[0,1]
        with self.assertRaisesRegex(ValueError,'signature_changed'):build(p,{'a':{'body':[f]}})
