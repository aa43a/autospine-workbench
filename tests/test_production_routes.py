from email.message import Message
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from autospine_workbench.automation.production_routes import dispatch_production


class ProductionRouteTests(unittest.TestCase):
    def handler(self):
        headers=Message();headers['Host']='127.0.0.1:8918'
        return SimpleNamespace(headers=headers,server=object(),_send_visual_json=Mock(),_send_bytes=Mock())

    def test_mutation_denied_before_manager_is_created(self):
        handler=self.handler()
        with patch('autospine_workbench.automation.production_routes.manager_for') as factory:
            self.assertTrue(dispatch_production(['api','production'],handler,'POST'))
            factory.assert_not_called()
        self.assertEqual(handler._send_visual_json.call_args.args[0],403)

    def test_bad_subroute_is_not_dispatched(self):
        handler=self.handler()
        self.assertTrue(dispatch_production(['api','production','id','erase'],handler,'POST'))
        self.assertEqual(handler._send_visual_json.call_args.args[0],404)

    def test_list_and_single_reads_attach_live_ownership_without_revising_the_run(self):
        row = dict(run_id='fixture', revision=7, status='running', stages={})
        manager = SimpleNamespace(get=Mock(return_value=row), list=Mock(return_value=[row]),
            execution_view=lambda value: dict(value, execution_active=False))
        for tail in ([], ['fixture']):
            handler = self.handler()
            with patch('autospine_workbench.automation.production_routes.manager_for', return_value=manager):
                dispatch_production(['api', 'production', *tail], handler, 'GET')
            status, response = handler._send_visual_json.call_args.args
            result = response['runs'][0] if not tail else response
            self.assertEqual(status, 200)
            self.assertIs(result['execution_active'], False)
            self.assertEqual(result['revision'], 7)
        self.assertNotIn('execution_active', row)

    def test_revision_preview_requires_mutation_authorization(self):
        handler=self.handler()
        with patch('autospine_workbench.automation.production_routes.manager_for') as factory:
            dispatch_production(['api','production','id','revision-plan'],handler,'POST')
            factory.assert_not_called()
        self.assertEqual(handler._send_visual_json.call_args.args[0],403)

    def test_work_record_requires_mutation_authorization_and_metrics_are_readonly(self):
        handler=self.handler()
        with patch('autospine_workbench.automation.production_routes.manager_for') as factory:
            dispatch_production(['api','production','id','work-sessions'],handler,'POST')
            factory.assert_not_called()
        self.assertEqual(handler._send_visual_json.call_args.args[0],403)
        handler=self.handler()
        dispatch_production(['api','production','id','metrics'],handler,'POST')
        self.assertEqual(handler._send_bytes.call_args.args[0],405)

    def test_revision_payload_passes_only_expected_fields(self):
        handler=self.handler();handler.headers['Origin']='http://127.0.0.1:8918'
        handler.headers['X-Autospine-Intent']='pipeline-preview'
        with patch('autospine_workbench.automation.production_routes.manager_for') as factory, \
             patch('autospine_workbench.automation.production_routes.read_json_object_request',
                   return_value={'expected_revision':3,'unexpected':True}):
            dispatch_production(['api','production','id','resume'],handler,'POST')
            factory.return_value.resume.assert_not_called()
        self.assertEqual(handler._send_visual_json.call_args.args[0],409)
