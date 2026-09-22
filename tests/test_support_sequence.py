from copy import deepcopy
import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.support_window_sequence import build


class SequenceTests(unittest.TestCase):
    def fixture(self):
        rows=[dict(time=i/10,root_shift=[0,0],angles={n:0 for n in ('thigh_l','calf_l','thigh_r','calf_r')}) for i in range(40)]
        anchors=[dict(limb='leg.'+s,start=0,end=5,target=[0,0]) for s in ('left','right')]
        return rows,anchors

    def test_failed_windows_preserve_reference(self):
        rows,anchors=self.fixture();original=deepcopy(rows)
        with patch('autospine_workbench.targets.character43.support_window_sequence.optimize',
                   side_effect=lambda d,n,r,a,l:(r,dict(status='no_improving_window_found'))):
            result,report=build({},'move',rows,anchors,20)
        self.assertEqual(rows,original);self.assertEqual(result,original)
        self.assertEqual(report['accepted_windows'],0)

    def test_changed_window_boundary_rejected(self):
        rows,anchors=self.fixture()
        def changed(d,n,r,a,l):
            out=deepcopy(r);out[0]['root_shift'][0]=1
            return out,dict(status='candidate')
        with patch('autospine_workbench.targets.character43.support_window_sequence.optimize',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'window_boundary_changed'):
                build({},'move',rows,anchors,20)

    def test_contact_switches_do_not_call_double_support_optimizer(self):
        rows,_=self.fixture()
        with patch('autospine_workbench.targets.character43.support_window_sequence.optimize') as solve:
            result,report=build({},'move',rows,[],20)
        solve.assert_not_called();self.assertEqual(result,rows)
        self.assertTrue(all(r['status']=='contact_transition_or_single_support_preserved' for r in report['windows']))
