import unittest
from copy import deepcopy
from test_motion_layer_edits import fixture, edits
from autospine_workbench.targets.character43.motion_layer_edits import validate, LayerEditError, edit_impact, apply


class RigEditProtocolTests(unittest.TestCase):
    def test_route_preserves_safe_structured_failure(self):
        from unittest.mock import patch
        from test_motion_adapt_route_body import handler_for
        from autospine_workbench.automation.motion_intake_routes import dispatch_motions
        from autospine_workbench.automation.pipeline_run import PipelineRunError
        error = PipelineRunError('motion_layer_transform_out_of_range')
        error.diagnostics = LayerEditError(str(error), '/layer_edits/transforms/0/scaleX', 'arm').diagnostics
        handler = handler_for(b'{}')
        with patch('autospine_workbench.automation.motion_target_jobs.submit', side_effect=error):
            dispatch_motions(['api', 'motions', 'source', 'adapt'], handler, 'POST')
        status, body = handler._send_visual_json.call_args.args
        self.assertEqual(status, 400)
        self.assertEqual(body['reason_code'], str(error))
        self.assertEqual(body['diagnostics'], error.diagnostics)

    def test_bad_field_has_pointer_and_does_not_mutate(self):
        value = edits()
        value['transforms'][0]['scaleX'] = 0
        before = deepcopy(value)
        with self.assertRaises(LayerEditError) as caught:
            validate(value, fixture())
        self.assertEqual(caught.exception.diagnostics[0]['path'], '/layer_edits/transforms/0/scaleX')
        self.assertEqual(caught.exception.diagnostics[0]['slot'], 'arm')
        self.assertEqual(value, before)

    def test_export_records_same_review_scope(self):
        value = edits()
        _, report, _ = apply(fixture(), 'move', value, [0, 1])
        self.assertEqual(report['edit_impact'], edit_impact(value))
        self.assertEqual(report['edit_impact']['execution'], 'full_build')
        self.assertEqual(report['edit_impact']['checks'], ['geometry', 'contact', 'occlusion', 'runtime'])

    def test_order_only_and_unknown_slot(self):
        value = edits()
        value['transforms'] = []
        value['draw_order'] = [row['name'] for row in fixture()['slots']][::-1]
        self.assertEqual(edit_impact(value)['checks'], ['occlusion', 'runtime'])
        value = edits()
        value['transforms'][0]['slot'] = 'missing'
        with self.assertRaises(LayerEditError) as caught:
            validate(value, fixture())
        self.assertEqual(caught.exception.diagnostics[0]['slot'], 'missing')
