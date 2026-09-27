from copy import deepcopy
import math
import unittest

from autospine_workbench.targets.character43.parent_pose_area_repair import compare, solve, verify_source
from autospine_workbench.targets.spine43.continuous_pose import area


class ParentPoseAreaRepairTests(unittest.TestCase):
    def test_real_sampling_records_scope_and_preserves_source_documents(self):
        from test_limb_transverse_repair import fixture
        from autospine_workbench.targets.character43.limb_transverse_repair import build
        parent=fixture();mesh=parent['skins'][0]['attachments']['leg']['leg']
        mesh['vertices']=[v for x,y in ((0,0),(0,10),(10,0))
                          for v in [2,1,x,y,.25,2,x,y,.75]]
        candidate,_=build(parent,'motion',['leg']);old_parent=deepcopy(parent);old_candidate=deepcopy(candidate)
        result=compare(parent,candidate,'motion','leg',.5)
        self.assertEqual(parent,old_parent);self.assertEqual(candidate,old_candidate)
        self.assertFalse(result['selected']);self.assertEqual(result['authority'],'none')
        self.assertEqual(result['parent_floor']['fixed_shift'],0)
        self.assertLessEqual(result['parent_floor']['maximum_shift'],result['budget_px']+1e-7)
        for time in (-1,2,float('nan')):
            with self.assertRaisesRegex(ValueError,'time_invalid'):compare(parent,candidate,'motion','leg',time)

    def test_restores_parent_compression_without_moving_fixed_vertices(self):
        original=[[0,0],[2,0],[1,.3]];parent=[[0,0],[2,0],[1,.45]]
        context=dict(row={'triangles':[[0,1,2]]},areas=[.5],edges=[(0,1),(1,2),(0,2)],
                     lengths=[2,math.sqrt(2),math.sqrt(2)],free=[False,False,True],budget=.2)
        result,evidence=solve(context,original,parent,[1])
        self.assertTrue(evidence['converged'])
        self.assertGreaterEqual(area(result,[0,1,2]),.45-1e-7)
        self.assertEqual(result[:2],original[:2])
        self.assertLessEqual(math.dist(result[2],original[2]),.2+1e-7)
        self.assertNotIn('minimum_ratios',context)

    def test_fixed_or_over_budget_counterexample_remains_failure(self):
        origin=[[0,0],[2,0],[1,.3]];parent=[[0,0],[2,0],[1,.45]]
        for free,budget in (([False]*3,.2),([False,False,True],.01)):
            context=dict(row={'triangles':[[0,1,2]]},areas=[.5],edges=[],lengths=[],free=free,budget=budget)
            result,evidence=solve(context,origin,parent,[1])
            self.assertFalse(evidence['converged'])
            self.assertLessEqual(max(math.dist(a,b) for a,b in zip(result,origin)),budget+1e-7)

    def test_baseline_must_share_all_other_motion_bind_and_slots(self):
        parent=dict(bones=[{'name':'a'}],slots=[{'name':'leg'}],skins=[{'attachments':{'leg':{}}}],
            animations={'move':{'bones':{},'attachments':{'default':{'leg':{'old':1},'other':{'keep':1}}}}})
        candidate=deepcopy(parent);candidate['animations']['move']['attachments']['default']['leg']={'new':2}
        verify_source(parent,candidate,'move','leg')
        for key,value in (('bones',[]),('slots',[]),('skins',[])):
            changed=deepcopy(candidate);changed[key]=value
            with self.assertRaisesRegex(ValueError,'unrelated_changes'):verify_source(parent,changed,'move','leg')
        candidate['animations']['move']['attachments']['default']['other']={'changed':True}
        with self.assertRaisesRegex(ValueError,'unrelated_changes'):verify_source(parent,candidate,'move','leg')
