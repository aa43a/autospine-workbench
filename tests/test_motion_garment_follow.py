import json
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from autospine_workbench.automation import motion_garment_follow as api
from autospine_workbench.automation import motion_repair_worker as worker
from autospine_workbench.automation.motion_repair_execution import GARMENT_PROFILE
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.motion_target_jobs import review_file
from autospine_workbench.resolved_project import canonical_sha256
from test_garment_follow_candidate import bundle


class GarmentWorkflowTests(unittest.TestCase):
    def test_download_preserves_compressed_evidence_and_rejects_changed_source(self):
        from autospine_workbench.automation import motion_target_jobs as jobs
        from autospine_workbench.targets.character43.garment_follow_scope import resolve
        from autospine_workbench.targets.character43.garment_follow_candidate import build
        from autospine_workbench.targets.character43.numeric_reference import read
        files,character=bundle()
        plan=dict(slot='garment',animation='motion',garment_follow=resolve(files,character,'garment','motion'))
        with patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'unavailable'}):
            output,_,_=build(files,character,plan)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);request={'character_sha256':'character'}
            (root/'request.json').write_bytes(canonical_bytes(request))
            manager=SimpleNamespace(folder=lambda _:root)
            with patch.object(jobs,'context',return_value=({'artifact_sha256':'candidate'},output)), \
                 patch.object(jobs,'assert_current') as current:
                raw=jobs.download(manager,'job')
                current.assert_called_once_with(manager,request)
                self.assertEqual(raw,jobs.download(manager,'job'))
                with ZipFile(BytesIO(raw)) as archive:
                    decoded={name:archive.read(name) for name in archive.namelist()}
                self.assertEqual(decoded,output)
                self.assertEqual(read(decoded),read(output))
                self.assertFalse(json.loads(decoded['motion-review.json'])['selected'])
                current.side_effect=RuntimeError('motion_target_character_changed')
                with self.assertRaisesRegex(RuntimeError,'character_changed'):jobs.download(manager,'job')

    def test_visual_entry_does_not_require_a_detected_geometry_failure(self):
        from autospine_workbench.automation.motion_visual_scope_event import validate
        files,_=bundle()
        body=dict(visual_inspection=True,triangle=-1,action='garment_follow',artifact_sha256='candidate',
                  slot='garment',animation='motion',time=.25)
        with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'candidate'},files)):
            event=validate(None,'job',body)
        self.assertEqual(event['time'],.25);self.assertFalse(event['detected_failure'])

    def test_readonly_capability_binds_character_and_parent_then_rejects_stale_sources(self):
        files, character = bundle()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); request = dict(character_sha256='character')
            (root/'request.json').write_bytes(canonical_bytes(request))
            store = Mock(); store.read.return_value = character
            manager = SimpleNamespace(folder=lambda _:root,
                character_manager=lambda:SimpleNamespace(application=SimpleNamespace(store=store)))
            with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'candidate'},files)), \
                 patch('autospine_workbench.automation.motion_target_jobs.assert_current'):
                raw,_ = review_file(manager,'job',['garment-follow','garment','motion.json'])
                value=json.loads(raw); self.assertTrue(value['available'])
                self.assertEqual(value['scope']['character_sha256'],'character')
                self.assertEqual(sorted(p.name for p in root.iterdir()),['request.json'])
                with self.assertRaisesRegex(RuntimeError,'candidate_changed'):
                    api.scope(manager,'job','garment','motion','old')
                raw,_ = review_file(manager,'job',['garment-follow','body','motion.json'])
                self.assertEqual(json.loads(raw)['reason_code'],'motion_garment_slot_undeclared')
                request['repair_execution']={'profile':'other'}
                (root/'request.json').write_bytes(canonical_bytes(request))
                raw,_ = review_file(manager,'job',['garment-follow','garment','motion.json'])
                self.assertFalse(json.loads(raw)['available'])

    def test_worker_dispatches_frozen_scope_and_fresh_downstream_checks_without_review(self):
        files, character = bundle()
        from autospine_workbench.targets.character43.garment_follow_scope import resolve
        scope=dict(resolve(files,character,'garment','motion'),character_sha256='character')
        plan=dict(action='garment_follow',slot='garment',animation='motion',artifact_sha256='parent',garment_follow=scope)
        request=dict(character_sha256='character',repair_execution=dict(profile=GARMENT_PROFILE,
            parent_job_id='parent-job',parent_artifact_sha256='parent',draft=plan,draft_sha256=canonical_sha256(plan)))
        store=Mock();store.read.side_effect=lambda digest:files if digest=='parent' else character
        store.publish.return_value='candidate'
        def depth(output,*args):
            output['motion-depth.json']=b'{"status":"not_evaluated"}'
            return {}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(worker,'AnimatedStore',return_value=store), \
             patch.object(worker,'progress') as progress, \
             patch.object(worker,'capture',return_value={'status':'mock_only'}) as capture, \
             patch('autospine_workbench.targets.character43.final_motion_contact.recheck',return_value={'status':'unavailable'}), \
             patch('autospine_workbench.automation.motion_repair_depth.recheck',side_effect=depth) as depth_call, \
             patch('autospine_workbench.automation.motion_repair_local_depth.run',return_value=None):
            worker.execute(Path(tmp),Path(tmp),Path(tmp),request)
            result=json.loads((Path(tmp)/'worker-result.json').read_bytes())
            self.assertEqual(result['repair_profile'],GARMENT_PROFILE)
            self.assertEqual(result['character_animation_status'],'needs_changes')
            self.assertFalse(result['production_authorized'])
            self.assertEqual(capture.call_count,1);self.assertEqual(depth_call.call_count,1)
            self.assertTrue({'garment_follow','garment_validate','depth_overlap'} <= {c.args[1] for c in progress.call_args_list})
            output=store.publish.call_args.args[0]
            self.assertEqual(json.loads(output['motion-repair-provenance.json'])['draft'],plan)
            with patch('autospine_workbench.automation.motion_target_jobs.context',return_value=({'artifact_sha256':'candidate'},output)):
                raw,_=review_file(None,'job',['repair-summary.json'])
            self.assertEqual(json.loads(raw)['garment_follow']['roots'],scope['roots'])
            # A source change must be rejected before any second build or capture.
            request['character_sha256']='different'
            with self.assertRaisesRegex(ValueError,'character_changed'):
                worker.execute(Path(tmp),Path(tmp),Path(tmp),request)
            self.assertEqual(capture.call_count,1)
