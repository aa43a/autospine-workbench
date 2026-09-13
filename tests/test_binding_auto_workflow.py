from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import json
from autospine_workbench.automation.binding_auto_workflow import prepare_and_apply


class WorkflowTests(unittest.TestCase):
    def test_adoption_uses_prepared_identity_and_reports_preparation_only_change(self):
        with TemporaryDirectory() as root:
            store = SimpleNamespace(state_root=Path(root))
            @contextmanager
            def source(*_):
                yield SimpleNamespace(source_addresses=dict(resolved_project_sha256='r', input_identity_sha256='new'))
            result = dict(changed=False, status='succeeded', reason_code='safe_bindings_exhausted',
                          rounds=0, batches=[], changed_layer_ids=[], authority='none', production_authorized=False)
            with patch('autospine_workbench.automation.binding_auto_workflow.complete_bindings', return_value=dict(changed=True, added_options=3, authority='none')) as complete, \
                 patch('autospine_workbench.automation.binding_auto_workflow.load_inputs', source), \
                 patch('autospine_workbench.automation.binding_auto_workflow.apply_all', return_value=result) as adopt:
                value = prepare_and_apply(store, 'p', 'r', 'old')
                complete.assert_called_once_with(store, 'p', 'r', 'old')
                adopt.assert_called_once_with(store, 'p', 'new')
                self.assertTrue(value['changed'])
                self.assertEqual(value['changed_layer_ids'], [])
                from jsonschema import Draft202012Validator
                schema = json.loads((Path(__file__).parents[1] / 'schemas/binding-auto-workflow-v1.schema.json').read_bytes())
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(value)
                adopt.side_effect = OSError('interruption')
                stopped = prepare_and_apply(store, 'p', 'r', 'old')
                self.assertEqual(stopped['status'], 'stopped')
                self.assertTrue(stopped['candidate_preparation']['changed'])
                complete.side_effect = ValueError('stale input')
                with self.assertRaisesRegex(ValueError, 'stale input'):
                    prepare_and_apply(store, 'p', 'r', 'stale')
