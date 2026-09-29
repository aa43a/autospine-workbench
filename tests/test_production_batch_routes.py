from email.message import Message
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from autospine_workbench.automation.production_batch_routes import dispatch_batches


class BatchRouteTests(TestCase):
    def handler(self):
        headers = Message(); headers['Host'] = '127.0.0.1:8918'
        return SimpleNamespace(headers=headers, server=object(), _send_visual_json=Mock(), _send_bytes=Mock())

    def test_mutation_checks_before_creating_manager(self):
        handler = self.handler()
        with patch('autospine_workbench.automation.production_batch_routes.manager_for') as factory:
            dispatch_batches(['api', 'production-batches'], handler, 'POST')
            factory.assert_not_called()
        self.assertEqual(handler._send_visual_json.call_args.args[0], 403)

    def test_unknown_route_and_readonly_compatibility(self):
        for tail, method, status in [(['id', 'erase'], 'POST', 404), (['id', 'compatibility'], 'POST', 405)]:
            handler = self.handler()
            dispatch_batches(['api', 'production-batches', *tail], handler, method)
            sender = handler._send_bytes if status == 405 else handler._send_visual_json
            self.assertEqual(sender.call_args.args[0], status)
