"""Same-origin policy boundary, exact-source CAS and explicit undo requests."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from tests import test_pipeline_web_http as fixtures


class SimpleBindingHttpTests(unittest.TestCase):
    setUp=fixtures.PipelineWebHttpTests.setUp
    close_server=fixtures.PipelineWebHttpTests.close_server
    request=fixtures.PipelineWebHttpTests.request
    document=fixtures.PipelineWebHttpTests.document

    def test_policy_routes_and_mutation_guards(self):
        self.base+='/animated/binding-policy'
        @contextmanager
        def source(*args):
            yield SimpleNamespace(source_addresses={'resolved_project_sha256':'a'*64,'input_identity_sha256':'b'*64})
        with patch('autospine_workbench.automation.simple_binding_routes.overview',return_value={'authority':'none'}) as read, \
             patch('autospine_workbench.automation.simple_binding_routes.load_inputs',source), \
             patch('autospine_workbench.automation.simple_binding_routes.apply',return_value={'changed':False}) as apply, \
             patch('autospine_workbench.automation.simple_binding_routes.apply_all',return_value={'changed':False}) as apply_all, \
             patch('autospine_workbench.automation.binding_auto_workflow.prepare_and_apply',return_value={'changed':False}) as workflow, \
             patch('autospine_workbench.automation.simple_binding_routes.undo',return_value={'changed':True}) as undo:
            self.assertEqual(self.request('GET')[0],200)
            self.assertEqual(self.request('OPTIONS')[0],204)
            self.assertEqual(self.request('DELETE')[0],405)
            body={'action':'apply','expected_resolved_sha256':'a'*64,'expected_input_sha256':'b'*64}
            self.assertEqual(self.request('POST',body=body,headers={'Origin':'http://evil.invalid'})[0],403)
            self.assertEqual(self.request('POST',body=body,headers={'X-Autospine-Intent':None})[0],403)
            self.assertEqual(self.request('POST',body={**body,'expected_input_sha256':'c'*64})[0],409)
            self.assertEqual(self.request('POST',body={**body,'approve_all':True})[0],400)
            apply.assert_not_called()
            self.assertEqual(self.request('POST',body=body)[0],200)
            apply.assert_called_once()
            self.assertEqual(self.request('POST',body={**body,'action':'apply_all'},headers={'Origin':'http://evil.invalid'})[0],403)
            apply_all.assert_not_called()
            self.assertEqual(self.request('POST',body={**body,'action':'apply_all'})[0],200)
            apply_all.assert_called_once()
            self.assertEqual(self.request('POST',body={**body,'action':'prepare_apply_all'},headers={'Origin':'http://evil.invalid'})[0],403)
            workflow.assert_not_called()
            self.assertEqual(self.request('POST',body={**body,'action':'prepare_apply_all'})[0],200)
            workflow.assert_called_once()
            self.assertEqual(self.request('POST',body={**body,'action':'undo'})[0],400)
            self.assertEqual(self.request('POST',body={**body,'action':'undo','decision_sha256':'d'*64})[0],200)
            undo.assert_called_once()
