"""Pipeline selection, fallback, recipe compatibility and cancellation boundaries."""
from contextlib import ExitStack
import unittest
from types import SimpleNamespace
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

    def run_trial(self, states, cancel=lambda: False):
        files = {'character-manifest.json': b'{"layers": []}'}; published = []
        def publish(output):
            published.append(output)
            return str(len(published))*64
        manager = SimpleNamespace(application=SimpleNamespace(store=SimpleNamespace(
            read=lambda _: files, publish=publish)))
        original = {'artifact_sha256': 'a'*64, 'manifest': {'layers': ['original']}}
        stages = []; mocks = []
        with ExitStack() as stack:
            for name, state in zip(('shoulder_boundary_candidate', 'shoulder_boundary_adaptive', 'shoulder_temporal'), states):
                report = dict(profile=name, status=state, geometry_passed=state=='needs_review', dense_boundary=[])
                mocks.append(stack.enter_context(patch(f'autospine_workbench.targets.character43.{name}.generate',
                                                      return_value=(files, report))))
            result = apply_selected(manager, {'shoulder_regions': ['layer-004']}, original,
                                    progress=stages.append, cancel_requested=cancel)
        return original, result, mocks, published, stages

    def test_selected_region_runs_bounded_refinement_and_preserves_source(self):
        original, result, mocks, published, stages = self.run_trial(['blocked', 'blocked', 'needs_review'])
        self.assertEqual(mocks[0].call_args.kwargs['slot_ids'], ['layer-004'])
        self.assertEqual(mocks[1].call_args.args[1], original['artifact_sha256'])
        self.assertEqual(mocks[2].call_args.args[3], '2'*64)
        self.assertEqual(result['artifact_sha256'], '3'*64)
        self.assertEqual(original['manifest']['layers'], ['original'])
        self.assertTrue(result['shoulder_trial']['included_in_candidate'])
        self.assertFalse(result['shoulder_trial']['selected'])
        self.assertEqual(len(published), 3)
        self.assertIn('shoulder-temporal', stages)

    def test_failure_keeps_original_artifact_and_exposes_trial(self):
        original, result, _, published, _ = self.run_trial(['blocked']*3)
        self.assertEqual(result['artifact_sha256'], original['artifact_sha256'])
        self.assertIs(result['manifest'], original['manifest'])
        self.assertEqual(result['shoulder_trial']['reason_code'], 'shoulder_geometry_blocked')
        self.assertEqual(len(published), 3)

    def test_pass_stops_without_running_additional_repairs(self):
        _, result, mocks, published, _ = self.run_trial(['needs_review', 'blocked', 'blocked'])
        mocks[1].assert_not_called(); mocks[2].assert_not_called()
        self.assertEqual(len(published), 1)
        self.assertEqual(result['shoulder_trial']['visual_contact_status'], 'not_evaluated')

    def test_cancel_stops_before_solver(self):
        with self.assertRaisesRegex(PipelineRunError, 'character_build_canceled'):
            self.run_trial(['needs_review']*3, cancel=lambda: True)

    def test_insufficient_contact_returns_original_but_integrity_errors_fail(self):
        original={'artifact_sha256':'a'*64}
        manager=SimpleNamespace(application=SimpleNamespace(store=SimpleNamespace(read=lambda _:{})))
        for reason in ('shoulder_boundary_contact_missing','shoulder_adaptive_trial_source_mismatch'):
            with patch('autospine_workbench.targets.character43.shoulder_boundary_candidate.generate',side_effect=ValueError(reason)):
                if 'source_mismatch' in reason:
                    with self.assertRaisesRegex(ValueError,reason):
                        apply_selected(manager,{'shoulder_regions':['layer-004']},original)
                else:
                    result=apply_selected(manager,{'shoulder_regions':['layer-004']},original)
                    self.assertEqual(result['artifact_sha256'],original['artifact_sha256'])
                    self.assertEqual(result['shoulder_trial']['reason_code'],reason)
