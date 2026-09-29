from email.message import Message
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from autospine_workbench.automation.production_entrance_routes import dispatch_entrances


class EntranceRoutes(TestCase):
    def test_mutation_authorization_before_reading_state(self):
        for tail in ([],['id','resume']):
            headers=Message();headers['Host']='127.0.0.1:8918'
            handler=SimpleNamespace(headers=headers,server=object(),_send_visual_json=Mock(),_send_bytes=Mock())
            with patch('autospine_workbench.automation.production_entrance_routes.manager_for') as manager:
                dispatch_entrances(['api','production-entrances',*tail],handler,'POST')
                manager.assert_not_called()
            self.assertEqual(handler._send_visual_json.call_args.args[0],403)
