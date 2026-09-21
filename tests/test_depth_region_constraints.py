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

    def test_interval_rows_keep_distinct_midpoint_evidence(self):
        p=dict(regions=[dict(source_slot='a',slot='a1',triangles=[0])])
        frames=[dict(time=t,source_tick=t*1e6,labels=[v],observed_states=s)
                for t,v,s in [(0,0,'N'),(.5,1,'F'),(1,1,'F')]]
        pair=build(p,{'a':{'body':frames}},interval_depth=True)[0]
        self.assertEqual(len(pair['samples']),2)
        row=pair['samples'][0]
        self.assertEqual(row['support'],'no_overlap')
        self.assertEqual(row['interval_sample']['tick'],500000)
        self.assertEqual(row['interval_sample']['current_front_slot'],'a1')
        frames[1]['time']=.4
        with self.assertRaisesRegex(ValueError,'midpoint_missing'):
            build(p,{'a':{'body':frames}},interval_depth=True)

    def test_disjoint_time_support_is_pruned_only_with_interval_evidence(self):
        p=dict(regions=[dict(source_slot=b,slot=b+'1',triangles=[0]) for b in ('a','b')])
        def frames(states):
            return [dict(time=t/2,source_tick=t*500000,labels=[1],observed_states=s) for t,s in enumerate(states)]
        models={'a':{'b':frames('FNF')},'b':{'a':frames('NBN')}}
        self.assertEqual(len(build(p,models)),2)
        stats={}
        self.assertEqual(build(p,models,interval_depth=True,diagnostics=stats),[])
        self.assertEqual(stats['pairs_disjoint_at_all_depth_samples'],2)
        models['b']['a'][0]['observed_states']='U'
        self.assertEqual(len(build(p,models,interval_depth=True)),2)
