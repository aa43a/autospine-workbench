from copy import deepcopy
import unittest
from unittest.mock import patch
from test_limb_transverse_repair import fixture
from autospine_workbench.targets.character43.limb_transverse_repair import build as compensate
from autospine_workbench.targets.character43.joint_boundary_animation import build


class BoundaryAnimationTests(unittest.TestCase):
    def test_preserves_unselected_bind_motion_and_all_requested_times(self):
        parent=fixture()
        parent['skins'][0]['attachments']['leg']['leg']['vertices']=[v for x,y in ((0,0),(0,10),(10,0))
            for v in (2,1,x,y,.5,2,x,y,.5)]
        before=deepcopy(parent)
        candidate,_=compensate(parent,'motion',['leg'],correction_frame='transverse',anchor_terminal=True)
        result,report=build(parent,candidate,'motion','leg',[0,.371,1])
        self.assertEqual(parent,before)
        for key in ('bones','slots','skins'):self.assertEqual(result[key],parent[key])
        self.assertEqual(result['animations']['motion']['bones'],parent['animations']['motion']['bones'])
        self.assertIn(.371,report['times']);self.assertFalse(report['selected'])
        self.assertEqual(report['key_count'],len(candidate['animations']['motion']['attachments']['default']['leg']['leg']['deform']))

    def test_midpoint_collapse_cannot_be_hidden_by_passing_key_solvers(self):
        parent=fixture();parent['bones'][2]['x']=200;parent['bones'][3]['x']=200
        parent['animations']['motion']['bones']['thigh_l']['scale'][1].update(x=1,y=1)
        mesh=parent['skins'][0]['attachments']['leg']['leg']
        mesh['vertices']=[v for x,y in ((0,0),(0,10),(10,0))
                          for v in (2,1,x,y,.5,2,x,y,.5)]
        candidate,_=compensate(parent,'motion',['leg'])
        calls=[]
        def solve(context,origin,previous,areas,**kwargs):
            calls.append(1)
            if len(calls)==1:return origin,{'converged':True}
            center=[sum(p[k] for p in origin)/3 for k in (0,1)]
            return [[2*center[k]-p[k] for k in (0,1)] for p in origin],{'converged':True}
        with patch('autospine_workbench.targets.character43.joint_boundary_animation.solve',side_effect=solve):
            _,report=build(parent,candidate,'motion','leg',[0,.5,1])
        self.assertEqual(report['solver_failures'],[])
        self.assertFalse(report['local_constraints_passed'])
        self.assertTrue(any(r['time']==.5 and r['triangles'] and not r['at_key'] for r in report['failures']))

    def test_invalid_validation_time_is_rejected_before_bake(self):
        parent=fixture();candidate,_=compensate(parent,'motion',['leg'])
        for time in (-1,2,float('nan')):
            with self.assertRaises(ValueError):build(parent,candidate,'motion','leg',[time])
