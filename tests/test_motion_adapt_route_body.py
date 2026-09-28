from email.message import Message
from io import BytesIO
from threading import RLock
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch
from autospine_workbench.automation.motion_intake_routes import dispatch_motions


def handler_for(raw):
    handler=Mock();headers=Message()
    for key,value in [('Host','127.0.0.1:8918'),('Origin','http://127.0.0.1:8918'),
                      ('X-Autospine-Intent','pipeline-preview'),('Content-Type','application/json'),
                      ('Content-Length',str(len(raw)))]:headers[key]=value
    handler.headers=headers;handler.rfile=BytesIO(raw)
    handler.server.automation_manager=SimpleNamespace(_lock=RLock(),_closed=False,_motions=Mock())
    return handler


class AdaptBodyTests(unittest.TestCase):
    def test_layer_order_body_over_old_1kb_limit_is_delivered(self):
        slots=['character-layer-%03d-region-attachment' % i for i in range(27)]
        body=dict(project_id='yaomeng',character_job_id='job-test',layer_edits=dict(
            profile='slot-world-affine-v1',draw_order=slots,transforms=[dict(slot=slots[0],dx=1,dy=0,rotation=10,scaleX=1,scaleY=1)]))
        raw=json.dumps(body).encode();self.assertGreater(len(raw),1024)
        handler=handler_for(raw)
        with patch('autospine_workbench.automation.motion_target_jobs.submit',return_value={'job_id':'new'}) as submit:
            dispatch_motions(['api','motions','source','adapt'],handler,'POST')
            self.assertEqual(submit.call_args.args[2],body)
            handler._send_visual_json.assert_called_once_with(202,{'job_id':'new'})

    def test_adapt_still_bounded_at_256kb(self):
        handler=handler_for(b' '*(256*1024+1))
        with patch('autospine_workbench.automation.motion_target_jobs.submit') as submit:
            dispatch_motions(['api','motions','source','adapt'],handler,'POST')
            submit.assert_not_called()
            self.assertEqual(handler._send_visual_json.call_args.args[0],413)
            self.assertEqual(handler._send_visual_json.call_args.args[1]['reason_code'],'request_too_large')

    def test_other_small_mutation_limit_unchanged(self):
        handler=handler_for(json.dumps({'padding':'x'*1100}).encode())
        with patch('autospine_workbench.automation.motion_repair_execution.submit') as submit:
            dispatch_motions(['api','motions','source','repair-execute'],handler,'POST')
            submit.assert_not_called()
            self.assertEqual(handler._send_visual_json.call_args.args[0],413)
