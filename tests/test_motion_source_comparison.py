import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_source_comparison import build
from autospine_workbench.resolved_project import canonical_sha256


class SourceComparisonTests(unittest.TestCase):
    def fixture(self, clip=None):
        source=dict(job_id='source',source_sha256='b'*64,
                    result=dict(fps=30,frame_count=91,duration_seconds=3))
        request=dict(source_job_id='source',source_job_sha256=canonical_sha256(source),clip=clip)
        manager=SimpleNamespace(folder=lambda _:Path('unused'),get=lambda _:source,
                                preview=lambda _:json.dumps(dict(frames=[dict(time=0),dict(time=3)])).encode())
        return manager, request, dict(artifact_sha256='a'*64,clip=clip)

    def test_full_and_clipped_time_offsets(self):
        for clip, expected in [(None,(0,3,3)),(dict(start_frame=30,end_frame=60),(1,2,1))]:
            manager,request,result=self.fixture(clip)
            with patch('autospine_workbench.automation.motion_source_comparison.read_document',return_value=request):
                report=build(manager,'target',result)
            self.assertEqual(tuple(report[k] for k in ('source_start','source_end','duration')),expected)
            self.assertEqual(report['artifact_sha256'],'a'*64)
            self.assertEqual(report['preview']['frames'][-1]['time'],3)

    def test_changed_source_or_clip_rejected(self):
        manager,request,result=self.fixture()
        with patch('autospine_workbench.automation.motion_source_comparison.read_document',return_value=request):
            result['clip']=dict(start_frame=0,end_frame=2)
            with self.assertRaisesRegex(Exception,'motion_target_clip_changed'):build(manager,'target',result)
            request['source_job_sha256']='different'
            with self.assertRaisesRegex(Exception,'motion_target_source_changed'):build(manager,'target',result)

    def test_verified_preview_failure_is_not_bypassed(self):
        manager,request,result=self.fixture()
        def reject(_):raise ValueError('motion_preview_changed')
        manager.preview=reject
        with patch('autospine_workbench.automation.motion_source_comparison.read_document',return_value=request):
            with self.assertRaisesRegex(ValueError,'motion_preview_changed'):build(manager,'target',result)
