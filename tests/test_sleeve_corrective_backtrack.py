import unittest
from copy import deepcopy
from autospine_workbench.asset.planning.sleeve_corrective_backtrack import backtrack
from autospine_workbench.asset.planning.cloth_anchor_correction import interpolate
from autospine_workbench.asset.planning.component_local_solver import metrics
from autospine_workbench.asset.planning.sleeve_helpers import make_helper
from tests.test_sleeve_helpers import SleeveHelperTests


class BacktrackTests(unittest.TestCase):
    def fixture(self):
        mesh,bones=SleeveHelperTests().fixture()
        helper,weights,cloth=make_helper(mesh,bones,[['hanging_cloth']]*3,'cloth')
        setup=mesh['vertices_xy'];tri=[[0,1,2]]
        row=dict(setup_vertices=setup,triangles=tri,weights=weights,correction_domain=dict(anchors=[0,1]))
        keys=[[[0.,0.],[0.,0.],[0.,0. if i in (0,16,32) else 10.]] for i in range(33)]
        qa=[]
        for tick in range(129):
            delta=interpolate(keys,tick)
            qa.append(metrics(setup,[[p[k]+d[k] for k in (0,1)] for p,d in zip(setup,delta)],tri))
        old=dict(drivers=['forearm','hand','cloth'],amplitudes=[0,0,0],trial_keys=keys,
                 correction_selected=True,qa=qa,failed_ticks=120,samples=[dict(points=setup) for _ in range(33)])
        trial=deepcopy(old);trial['trial_keys']=[[[ -v for v in p] for p in key] for key in keys]
        return row,bones+[helper],old,trial

    def test_half_step_repairs_overshoot_without_mutating_source(self):
        args=self.fixture();snapshot=deepcopy(args)
        result,evidence=backtrack(*args)
        self.assertEqual(result['failed_ticks'],0)
        self.assertEqual(result['backtrack']['fraction'],.5)
        self.assertEqual(result['anchor_displacement'],0)
        self.assertEqual(args,snapshot)

    def test_unchanged_trial_returns_exact_source(self):
        row,chain,old,_=self.fixture()
        result,evidence=backtrack(row,chain,old,old)
        self.assertIs(result,old);self.assertEqual(len(evidence),3)

    def test_incomplete_keys_and_mismatched_motion_rejected(self):
        row,chain,old,trial=self.fixture();trial['trial_keys'].pop()
        with self.assertRaisesRegex(ValueError,'keys'):backtrack(row,chain,old,trial)
        trial['amplitudes']=[1,0,0]
        with self.assertRaisesRegex(ValueError,'motion'):backtrack(row,chain,old,trial)
