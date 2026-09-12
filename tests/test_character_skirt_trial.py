"""Opt-in skirt application preserves default behavior and decision authority."""
import importlib.util
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from autospine_workbench.automation.character_skirt_trial import apply_selected, validate, PROFILE
from autospine_workbench.automation.pipeline_run import PipelineRunError
from autospine_workbench.automation.storage_io import canonical_bytes
from tests.test_character_skirt_candidate import fixture


class SkirtTrialTests(unittest.TestCase):
    def test_v2_selects_explicit_driver_without_changing_v1(self):
        from autospine_workbench.automation.character_skirt_trial import TORSO_PROFILE
        files = {'character-manifest.json': canonical_bytes({'layers': [
            dict(layer_id='skirt', name='bottomwear', state='static_reference')]})}
        store = SimpleNamespace(read=lambda _: files, publish=lambda _: 'b'*64)
        manager = SimpleNamespace(application=SimpleNamespace(store=store))
        report = dict(rows=[{'layer_id': 'skirt'}], geometry_passed=True, setup_error_px=0)
        with patch('autospine_workbench.targets.character43.skirt_candidate.generate', return_value=(files, report)) as build:
            for profile, options in [(PROFILE, {}), (TORSO_PROFILE, {'waist_driver': 'reviewed-chest-v1'})]:
                apply_selected(manager, {'skirt_profile': profile}, {'artifact_sha256': 'a'*64})
                self.assertEqual(build.call_args.kwargs, options)

    def test_unselected_path_is_identity(self):
        result = {'artifact_sha256': 'old', 'manifest': {}}
        self.assertIs(apply_selected(None, {}, result), result)
        for value in ('unsupported', {}, [], True):
            with self.assertRaises(PipelineRunError): validate(value)

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'optional Pillow')
    def test_trial_and_missing_eligible_layers(self):
        files = fixture(); saved = []
        store = SimpleNamespace(read=lambda _: files, publish=lambda f: saved.append(f) or 'b'*64)
        manager = SimpleNamespace(application=SimpleNamespace(store=store))
        result = {'artifact_sha256': 'a'*64, 'texture_trial': {'authority': 'none'}}
        value = apply_selected(manager, {'skirt_profile': PROFILE}, result)
        self.assertEqual(value['skirt_trial']['layer_ids'], ['skirt'])
        self.assertFalse(value['skirt_trial']['selected'])
        self.assertEqual(value['texture_trial'], result['texture_trial'])
        self.assertEqual(result['artifact_sha256'], 'a'*64)
        self.assertEqual(value['manifest']['layers'][0]['binding_decision'], {'action': 'pending'})
        manifest = json.loads(files['character-manifest.json'])
        manifest['layers'][0]['state'] = 'rigid_reviewed'
        files['character-manifest.json'] = canonical_bytes(manifest)
        with self.assertRaisesRegex(PipelineRunError, 'character_skirt_layers_missing'):
            apply_selected(manager, {'skirt_profile': PROFILE}, result)
