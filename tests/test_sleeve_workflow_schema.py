import json
from pathlib import Path
import unittest

try:
    import jsonschema
except ImportError:
    jsonschema = None

from autospine_workbench.automation.sleeve_final_status import finalize


@unittest.skipIf(jsonschema is None, 'optional JSON Schema validation dependency')
class SleeveWorkflowSchemaTests(unittest.TestCase):
    def test_terminal_quality_states_follow_runtime_contract(self):
        schema = json.loads((Path(__file__).parents[1] /
                             'schemas/sleeve-workflow-v1.schema.json').read_text())
        for failed in (0, 1):
            raw = dict(schema='autospine.sleeve-workflow/v1', run_id='run-'+'a'*64,
                       project_id='fixture', status='needs_review', steps=[],
                       runtime_status='core_passed', alpha_contact_status='not_evaluated',
                       framebuffer_review='framebuffer/index.html', authority='none',
                       production_authorized=False, records=[dict(
                           layer_id='layer-001', component_id='component-0000',
                           status='candidate_exported', download='candidate.zip',
                           runtime_status='core_passed', reason_code='pending',
                           official_framebuffer=dict(failed_samples=failed))])
            final = finalize(raw)
            jsonschema.validate(final, schema)
            self.assertEqual(final['status'], 'blocked' if failed else 'needs_review')
            final['production_authorized'] = True
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(final, schema)
