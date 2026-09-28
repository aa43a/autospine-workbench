import json
import unittest
from unittest.mock import patch
from test_motion_target_intake import inputs
from autospine_workbench.automation.motion_target_worker import build_candidate


class TimePreflightTests(unittest.TestCase):
    def test_repair_grid_keeps_event_and_avoids_duplicate_runtime_key(self):
        from test_character_affine_repair import fixture
        from autospine_workbench.targets.character43.affine_area_repair import repair
        from autospine_workbench.targets.character43.runtime_storage_reference import f32, require_distinct_times
        doc=fixture()
        doc['animations']['walk']['bones']['a']['scale'].insert(1,dict(time=.50000001,x=.7,y=1))
        with patch('autospine_workbench.targets.character43.affine_area_repair.project',side_effect=lambda c,p:p):
            result,_=repair(doc,'walk',samples=3)
        keys=result['animations']['walk']['attachments']['default']['mesh']['mesh']['deform']
        self.assertIn(.50000001,[k['time'] for k in keys])
        self.assertNotIn(.5,[k['time'] for k in keys])
        require_distinct_times([dict(time=f32(k['time'])) for k in keys])

    def test_layer_bake_preserves_event_over_generated_alias(self):
        from test_motion_layer_edits import fixture, edits
        from autospine_workbench.targets.character43.motion_layer_edits import apply
        from autospine_workbench.targets.character43.runtime_storage_reference import f32, require_distinct_times
        doc=fixture()
        doc['animations']['move']['bones']['root']['rotate'].insert(1,dict(time=.50000001,value=22.5))
        result,report,times=apply(doc,'move',edits(),[0,.5,.50000001,1])
        self.assertIn(.50000001,times)
        self.assertNotIn(.5,times)
        self.assertTrue(report['synthetic_time_aliases'])
        require_distinct_times([dict(time=f32(t)) for t in times])

    def test_distinct_events_fail_before_expensive_repair(self):
        args=inputs()
        doc=json.loads(args[0]['skeleton.json'])
        doc['animations']={'external-motion':{'bones':{}}}
        with patch('autospine_workbench.automation.motion_target_pose.project',return_value=(doc,{})), \
             patch('autospine_workbench.automation.motion_target_pose.correct') as correct:
            with self.assertRaisesRegex(ValueError,'distinct_times_collide'):
                build_candidate(*args,character_digest='a'*64,motion_digest='b'*64,
                                moving_ankles={'times':[0,1,1+1e-9]})
            correct.assert_not_called()
