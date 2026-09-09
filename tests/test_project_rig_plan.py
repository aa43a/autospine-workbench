"""Real planner reports with exact project identity and immutable cached reads."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

from tests.test_rig_planner import fixture
from autospine_workbench.automation import project_rig_plan as module
from autospine_workbench.resolved_project import canonical_sha256


class ProjectRigPlanTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = SimpleNamespace(state_root=Path(temp.name))
        candidate, skeleton, bindings, draft, images = fixture()
        candidate['canvas'] = [4, 4]
        self.addresses = dict(input_identity_sha256='a' * 64, resolved_project_sha256='b' * 64,
                              semantic_candidate_sha256=canonical_sha256(candidate),
                              skeleton_candidate_sha256=canonical_sha256(skeleton),
                              layer_bindings_sha256=canonical_sha256(bindings),
                              layer_binding_draft_sha256=canonical_sha256(draft))
        self.info = dict(candidate=candidate, bindings=bindings, draft=draft, source_addresses=self.addresses)
        self.source = SimpleNamespace(candidate=candidate, skeleton=skeleton, bindings=bindings,
                                      draft=draft, images=images, source_addresses=self.addresses,
                                      assert_current=lambda: None)
        @contextmanager
        def load(*_):
            yield self.source
        for name, value in [('inspect_registration', lambda *_: deepcopy(self.info)),
                            ('assert_registered_current', lambda *_: None),
                            ('load_inputs', load),
                            ('_registrations', lambda *_: [('0' * 64, {'manifest': {'dataset_id': 'test'}})])]:
            patcher = patch.object(module, name, value)
            patcher.start(); self.addCleanup(patcher.stop)

    def prepare(self):
        return module.prepare_plan(self.store, 'project', 'b' * 64, 'a' * 64)

    def test_full_coverage_cache_idempotence_and_no_decision_changes(self):
        before = deepcopy(self.info)
        self.assertEqual(module.read_plan(self.store, 'project')['status'], 'missing')
        result = self.prepare()
        self.assertEqual(result['plan']['scope'], ['layer-000'])
        self.assertEqual(result['plan']['layers'][0]['strategy'], 'facial')
        self.assertGreater(result['plan']['layers'][0]['evidence']['component_count'], 0)
        self.assertEqual(self.info, before)
        with patch.object(module, 'build', side_effect=AssertionError('cache must not rerun analysis')):
            self.assertEqual(self.prepare(), result)
            self.assertEqual(module.read_plan(self.store, 'project'), result)
        self.assertFalse(result['plan']['production_authorized'])
        import jsonschema
        schema = json.loads(Path('schemas/project-rig-plan-status-v1.schema.json').read_text('utf-8'))
        schema['properties']['plan'] = json.loads(Path('schemas/rig-plan-v1.schema.json').read_text('utf-8'))
        jsonschema.validate(result, schema)

    def test_new_saved_decision_gets_a_new_plan_without_reusing_old_status(self):
        old = self.prepare()
        self.info['draft']['records'][0].update(action='bind', option_id='rigid:head')
        self.addresses.update(input_identity_sha256='c' * 64,
                              layer_binding_draft_sha256=canonical_sha256(self.info['draft']))
        self.assertEqual(module.read_plan(self.store, 'project')['status'], 'missing')
        current = module.prepare_plan(self.store, 'project', 'b' * 64, 'c' * 64)
        self.assertNotEqual(old['plan_sha256'], current['plan_sha256'])
        self.assertEqual(current['plan']['layers'][0]['existing_action'], 'bind')

    def test_missing_image_produces_analysis_reason_and_no_current_plan(self):
        self.source.images.clear()
        with self.assertRaisesRegex(ValueError, 'project_rig_plan_analysis_failed'):
            self.prepare()
        self.assertEqual(module.read_plan(self.store, 'project')['status'], 'missing')

    def test_stale_and_changed_sources_cannot_expose_old_plan(self):
        self.prepare()
        for resolved, identity in [('c' * 64, 'a' * 64), ('b' * 64, 'c' * 64)]:
            with self.assertRaisesRegex(ValueError, 'animated_review_conflict'):
                module.prepare_plan(self.store, 'project', resolved, identity)
        self.addresses['input_identity_sha256'] = 'd' * 64
        self.assertEqual(module.read_plan(self.store, 'project')['status'], 'missing')

    def test_inventory_and_decision_tamper_rejected(self):
        result = self.prepare()
        for mutate in [lambda p: p.update(scope=[]),
                       lambda p: p['layers'][0].update(existing_action='bind'),
                       lambda p: p.update(production_authorized=True),
                       lambda p: p.update(source_draft_sha256='0' * 64)]:
            plan = deepcopy(result['plan']); mutate(plan)
            with self.assertRaisesRegex(ValueError, 'project_rig_plan_source_mismatch'):
                module.validate_sources(plan, self.info)
        folder = module._folder(self.store, 'project')
        (folder / ('a' * 64 + '.json')).write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'project_rig_plan_invalid'):
            module.read_plan(self.store, 'project')
