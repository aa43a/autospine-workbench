import unittest
from unittest.mock import patch
from autospine_workbench.targets.character43.depth_order_continuity_guard import build


class ContinuityGuardTests(unittest.TestCase):
    def test_bad_region_is_retained_while_independent_requirements_continue(self):
        depth={'strict_interval_evidence':True,'pairs':[dict(arm_slot=n,torso_slot='body') for n in ('a','b')]}
        seen=[];probe=object()
        def subset(doc,animation,proposal,actual_probe):
            self.assertIs(probe,actual_probe);seen.append(proposal)
            return {'candidate':True},dict(excluded=[])
        checks=iter([dict(status='needs_review',records=[dict(changed_region='a',body='body')]),
                     dict(status='no_sampled_cut',records=[])])
        with patch('autospine_workbench.targets.character43.depth_order_continuity_guard.subset_build',side_effect=subset):
            candidate,report=build({},'move',depth,probe,lambda c:next(checks))
        self.assertIsNotNone(candidate);self.assertEqual(report['status'],'partial_candidate')
        self.assertEqual(seen[-1]['pairs'],[dict(arm_slot='b',torso_slot='body')])
        self.assertTrue(all(row['strict_interval_evidence'] for row in seen))
        self.assertEqual(len(depth['pairs']),2);self.assertFalse(report['selected'])

    def test_unmeasured_check_does_not_return_candidate_or_discard_evidence(self):
        with patch('autospine_workbench.targets.character43.depth_order_continuity_guard.subset_build',
                   return_value=({'candidate':True},dict(excluded=[]))):
            candidate,report=build({},'move',{'pairs':[dict(arm_slot='a',torso_slot='body')]},object(),
                lambda c:dict(status='incomplete',records=[]))
        self.assertIsNone(candidate);self.assertEqual(report['excluded'],[])
        self.assertEqual(report['attempts'][0]['continuity']['status'],'incomplete')

    def test_unchanged_result_is_not_a_successful_repair_candidate(self):
        with patch('autospine_workbench.targets.character43.depth_order_continuity_guard.subset_build',
                   return_value=({},dict(excluded=[]))):
            candidate,report=build({},'move',{'pairs':[dict(arm_slot='a',torso_slot='body')]},object(),
                lambda c:dict(status='no_sampled_cut',records=[]))
        self.assertIsNone(candidate)
        self.assertEqual(report['status'],'no_supported_order_change')


if __name__=='__main__':unittest.main()
