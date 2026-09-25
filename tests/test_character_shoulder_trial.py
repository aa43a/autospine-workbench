"""Pipeline selection, fallback, recipe compatibility and cancellation boundaries."""
import unittest
from unittest.mock import patch

from autospine_workbench.automation.character_shoulder_trial import apply_selected, validate
from autospine_workbench.automation.character_build_options import valid_options
from autospine_workbench.automation.pipeline_run import PipelineRunError


class ShoulderTrialTests(unittest.TestCase):
    def test_default_preserves_identity_without_reading_store(self):
        original = {'artifact_sha256': 'a'*64}
        self.assertIs(apply_selected(None, {}, original), original)
        for bad in ([], ['x', 'x'], ['../x'], True, 'x', [1], ['x']*17):
            with self.assertRaises(PipelineRunError): validate(bad)

    def test_legacy_recipe_and_region_recipe_validation(self):
        self.assertTrue(valid_options({'skirt_profile': 'fixed-waist-three-chain-v1'}))
        self.assertTrue(valid_options({'shoulder_regions': ['layer-004']}))
        for bad in ({'other': 'x'}, {'shoulder_regions': []}, {'skirt_profile': []}):
            self.assertFalse(valid_options(bad))

    def test_legacy_request_does_not_run_solver_or_read_store(self):
        original={'artifact_sha256':'a'*64,'issues':[{'reason':'geometry_failure'}]}
        request={'shoulder_regions':['layer-004']}
        with patch('autospine_workbench.targets.character43.shoulder_boundary_candidate.generate') as solver:
            result=apply_selected(None,request,original)
            solver.assert_not_called()
        self.assertEqual(result['artifact_sha256'],original['artifact_sha256'])
        self.assertIs(result['issues'],original['issues'])
        trial=result['shoulder_trial']
        self.assertEqual(trial['status'],'not_applied')
        self.assertEqual(trial['reason_code'],'shoulder_boundary_constraint_retired')
        self.assertFalse(trial['included_in_candidate'])
        self.assertEqual(trial['attempts'],[])
        self.assertEqual(trial['visual_contact_status'],'not_evaluated')
        self.assertNotIn('shoulder_trial',original)
        self.assertEqual(request,{'shoulder_regions':['layer-004']})

    def test_cancel_still_honored(self):
        with self.assertRaisesRegex(PipelineRunError,'character_build_canceled'):
            apply_selected(None,{'shoulder_regions':['layer-004']},{},cancel_requested=lambda:True)
