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

    def test_revision_payload_passes_only_expected_fields(self):
        handler=self.handler();handler.headers['Origin']='http://127.0.0.1:8918'
        handler.headers['X-Autospine-Intent']='pipeline-preview'
        with patch('autospine_workbench.automation.production_routes.manager_for') as factory, \
             patch('autospine_workbench.automation.production_routes.read_json_object_request',
                   return_value={'expected_revision':3,'unexpected':True}):
            dispatch_production(['api','production','id','resume'],handler,'POST')
            factory.return_value.resume.assert_not_called()
        self.assertEqual(handler._send_visual_json.call_args.args[0],409)
