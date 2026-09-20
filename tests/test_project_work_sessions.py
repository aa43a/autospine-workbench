import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
from jsonschema import Draft202012Validator
from autospine_workbench.automation.project_work_sessions import overview, save


class WorkSessionsTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.source={'sha256':'a'*64}
        self.manager=SimpleNamespace(root=Path(temp.name),_lock=RLock(),projects=SimpleNamespace(get_project=lambda p:{'source':self.source}))
        self.segment=dict(session_id='a'*32,stage='joints',started_at='2026-09-20T10:00:00Z',ended_at='2026-09-20T10:01:00Z',seconds=60,method='operator_stopwatch_segment_v1')

    def write(self, payload, action='record', current=None):
        current=current or overview(self.manager,'p')
        return save(self.manager,'p',dict(expected_head_sha256=current['head_sha256'],expected_source_sha256=current['source_sha256'],action=action,payload=payload))

    def test_append_revoke_preserves_history_and_unknown_total(self):
        self.assertIsNone(overview(self.manager,'p')['metrics']['recorded_minutes'])
        result=self.write(self.segment)
        self.assertEqual(result['metrics']['recorded_minutes'],1)
        self.assertIsNone(result['metrics']['total_human_minutes'])
        self.assertIsNone(result['metrics']['stage_minutes']['sleeves'])
        schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/project-work-session-v1.schema.json').read_bytes())
        path=self.manager.root/'work-sessions/p/000000.json'
        original=path.read_bytes();Draft202012Validator(schema).validate(json.loads(original))
        result=self.write('a'*32,'revoke')
        self.assertIsNone(result['metrics']['recorded_minutes']);self.assertEqual(path.read_bytes(),original)

    def test_conflict_overlap_duplicate_and_source_changes(self):
        old=overview(self.manager,'p');self.write(self.segment)
        with self.assertRaisesRegex(RuntimeError,'conflict'):self.write(self.segment,current=old)
        with self.assertRaisesRegex(RuntimeError,'duplicate'):self.write(self.segment)
        with self.assertRaisesRegex(RuntimeError,'overlap'):self.write(dict(self.segment,session_id='b'*32))
        current=overview(self.manager,'p');self.source={'sha256':'b'*64}
        self.assertEqual(overview(self.manager,'p')['sessions'],[])
        with self.assertRaisesRegex(RuntimeError,'conflict'):self.write(dict(self.segment,session_id='c'*32),current=current)

    def test_invalid_clocks_and_durations_rejected_without_write(self):
        for changes in [dict(seconds=True),dict(seconds=float('nan')),dict(seconds=500),dict(started_at='no'),dict(ended_at='2026-09-19T10:00:00Z'),dict(stage='invented')]:
            with self.assertRaisesRegex(RuntimeError,'invalid'):self.write(dict(self.segment,**changes))
        self.assertIsNone(overview(self.manager,'p')['head_sha256'])
