from email.message import Message
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from autospine_workbench.automation.production_delivery_routes import dispatch_deliveries


class DeliveryRoutes(TestCase):
    def handler(self):
        headers=Message();headers['Host']='127.0.0.1:8918'
        return SimpleNamespace(headers=headers,server=object(),_send_visual_json=Mock(),_send_bytes=Mock())

    def test_mutation_auth_precedes_state_access(self):
        for tail in ([],['id','resume'],['id','review']):
            handler=self.handler()
            with patch('autospine_workbench.automation.production_delivery_routes.manager_for') as factory:
                dispatch_deliveries(['api','production-deliveries',*tail],handler,'POST')
                factory.assert_not_called()
            self.assertEqual(handler._send_visual_json.call_args.args[0],403)

    def test_download_and_player_are_readonly(self):
        for tail in (['id','download'],['id','view','player.html']):
            handler=self.handler()
            dispatch_deliveries(['api','production-deliveries',*tail],handler,'POST')
            self.assertEqual(handler._send_bytes.call_args.args[0],405)
