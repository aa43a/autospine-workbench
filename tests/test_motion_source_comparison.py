import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_source_comparison import build, link
from autospine_workbench.resolved_project import canonical_sha256


class SourceComparisonTests(unittest.TestCase):
    def fixture(self, clip=None):
        identity=dict(motion_ir_sha256='c'*64,bundle_sha256='d'*64)
        source=dict(job_id='source',source_sha256='b'*64,status='succeeded',
                    result=dict(fps=30,frame_count=91,duration_seconds=3,motion=identity))
        request=dict(job_id='target',kind='adapt',source_job_id='source',
                     source_job_sha256=canonical_sha256(source),clip=clip,motion_identity=dict(identity))
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

    def test_wrong_compilation_and_missing_source_identity_rejected(self):
        for identity in ({},dict(motion_ir_sha256='wrong',bundle_sha256='d'*64)):
            manager,request,result=self.fixture();request['motion_identity']=identity
            with patch('autospine_workbench.automation.motion_source_comparison.read_document',return_value=request):
                with self.assertRaisesRegex(Exception,'source_identity_mismatch'):link(manager,'target',result)

    def test_invalid_sampling_is_not_a_valid_time_range(self):
        for change in (dict(fps=True),dict(fps=float('nan')),dict(frame_count=0),
                       dict(frame_count=91.0),dict(duration_seconds=4),dict(duration_seconds=float('inf'))):
            manager,request,result=self.fixture();source=manager.get('source')
            source['result'].update(change);request['source_job_sha256']='fixture-source'
            # NaN/inf cannot enter canonical storage, but fail closed even under a corrupt reader.
            with patch('autospine_workbench.automation.motion_source_comparison.read_document',return_value=request), \
                 patch('autospine_workbench.automation.motion_source_comparison.canonical_sha256',return_value=request['source_job_sha256']):
                with self.assertRaisesRegex(Exception,'time_invalid'):link(manager,'target',result)

    def test_source_link_route_avoids_large_artifacts_and_preview_loading(self):
        from autospine_workbench.automation.motion_target_jobs import review_file
        manager,request,result=self.fixture(dict(start_frame=30,end_frame=60));source=manager.get('source')
        manager.get=lambda key:source if key=='source' else dict(kind='adapt',status='succeeded',result=result)
        manager.preview=lambda _:self.fail('small source binding must not load preview')
        with patch('autospine_workbench.automation.motion_source_comparison.read_document',return_value=request), \
             patch('autospine_workbench.automation.motion_target_jobs.context',side_effect=AssertionError('bundle read')):
            raw,mime=review_file(manager,'target',['source-link.json'])
        value=json.loads(raw);self.assertEqual(mime,'application/json')
        self.assertEqual((value['source_start'],value['source_end'],value['duration']),(1,2,1))
        self.assertEqual(value['motion_identity'],request['motion_identity'])
        self.assertEqual(value['target_job_id'],'target');self.assertNotIn('preview',value)
