from copy import deepcopy
import unittest
from unittest.mock import patch
from tests.test_retained_sleeve_domains import module


def result(area,inversions,bad,key):
    qa=dict(min_area_ratio=area,max_area_ratio=1.,max_edge_stretch=1.,inversions=inversions,bad_triangles=bad)
    failed=129 if area<.5 or inversions else 0
    return dict(bone_id='motion',amplitudes=[0,30,0],qa=[qa]*129,failed_ticks=failed,
        trial_failed_ticks=failed,reason_codes=['test'],correction_selected=True,
        trial_keys=[[[key,0.]] for _ in range(33)])


class RetainedPassTests(unittest.TestCase):
    def test_rejected_keys_can_seed_but_never_replace_retained_result(self):
        old=result(.3,0,[0],0.);snapshot=deepcopy(old)
        rejected=result(.2,1,[0,1],5.);good=result(1.,0,[],2.)
        with patch.object(module,'track',side_effect=[rejected,good]) as solver:
            chosen,evidence=module.solve_track(dict(layer_id='fixture',setup_vertices=[[0.,0.]]),[],old,smooth=True,blend=False,passes=3)
        self.assertIs(chosen,good);self.assertEqual(old,snapshot)
        self.assertEqual(solver.call_count,2)
        self.assertEqual(solver.call_args_list[1].kwargs['key_seeds'][4],[[5.,0.]])
        self.assertFalse(evidence['rounds'][0]['selected']);self.assertTrue(evidence['rounds'][1]['selected'])

    def test_all_rejected_rounds_preserve_exact_source_and_limit(self):
        old=result(.3,0,[0],0.);bad=result(.2,1,[0,1],5.)
        with patch.object(module,'track',return_value=bad) as solver:
            chosen,evidence=module.solve_track(dict(layer_id='fixture',setup_vertices=[[0.,0.]]),[],old,smooth=True,blend=False,passes=3)
        self.assertIs(chosen,old);self.assertEqual(solver.call_count,3)
        self.assertFalse(evidence['selected'])
        with self.assertRaisesRegex(ValueError,'passes'):
            module.solve_track({},[],old,smooth=True,blend=False,passes=4)
