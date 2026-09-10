import unittest
from copy import deepcopy
from autospine_workbench.asset.planning.sleeve_repair_policy import eligible, select


def report(bad=False):
    qa=dict(inversions=0,min_area_ratio=.4 if bad else 1.,max_area_ratio=1.,max_edge_stretch=1.,bad_triangles=[0] if bad else [])
    row=dict(layer_id='layer-a',component_id='component-a',triangles=[[0,1,2]],setup_vertices=[[0,0],[1,0],[0,1]],helper={},
        setup_error=0.,weight_sum_error=0.,tracks=[dict(bone_id=str(i),amplitudes=[1,0,0],drivers=['a','b','c'],
        anchor_displacement=0.,loop_error=0.,qa=[deepcopy(qa) for _ in range(129)]) for i in range(7)])
    return dict(schema='autospine.sleeve-motion-envelope/v1',project_id='any-name',skeleton_sha256='a'*64,
        source_sha256='b'*64,authority='none',production_authorized=False,records=[row])


class SleeveRepairPolicyTests(unittest.TestCase):
    def test_trigger_uses_failed_hand_ownership(self):
        r=report(True)['records'][0]
        self.assertTrue(eligible(r,[dict(role='hand')]))
        for role in ('unknown','cuff','hanging_cloth','sleeve'):
            self.assertFalse(eligible(r,[dict(role=role)]))
        self.assertFalse(eligible(report()['records'][0],[dict(role='hand')]))

    def test_fully_passed_improvement_preserves_other_region(self):
        old=report(True);trial=report();other=deepcopy(trial['records'][0]);other['layer_id']='other'
        old['records'].append(deepcopy(other));trial['records'].append(other)
        snapshot=deepcopy(old)
        value,decisions=select(old,trial,{('layer-a','component-a')})
        self.assertTrue(decisions[0]['selected']);self.assertFalse(decisions[1]['selected'])
        self.assertEqual(value['records'][1],old['records'][1]);self.assertEqual(old,snapshot)
        self.assertFalse(value['production_authorized'])

    def test_no_gain_or_partial_trial_retains_exact_baseline(self):
        for old,trial in ((report(),report()),(report(True),report(True))):
            value,_=select(old,trial,{('layer-a','component-a')})
            self.assertEqual(value,old)

    def test_source_geometry_and_motion_mismatch_rejected(self):
        for mutate in (lambda x:x.update(project_id='wrong'),
                       lambda x:x['records'][0].update(triangles=[[2,1,0]]),
                       lambda x:x['records'][0]['tracks'][0].update(amplitudes=[99,0,0])):
            trial=report();mutate(trial)
            with self.assertRaises(ValueError):select(report(True),trial,{('layer-a','component-a')})
