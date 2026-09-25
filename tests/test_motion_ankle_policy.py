from types import SimpleNamespace
from unittest.mock import patch
import unittest

from autospine_workbench.automation.motion_ankle_policy import PROFILE, select, prepare
from autospine_workbench.automation.motion_target_comparison import signature


class MotionAnklePolicyTests(unittest.TestCase):
    def request(self, **changes):
        return dict(moving_ankle_profile=PROFILE, contact_correction=False, **changes)

    def test_legacy_and_valid_strategy(self):
        self.assertIsNone(select({}))
        self.assertEqual(select(self.request()), PROFILE)
        for changes in ({'contact_correction':True}, {'contact_correction':0},
                        {'clip':{}}, {'moving_ankle_profile':None},
                        {'pose_profile':'source-pose-post-contact-timeline-v2'}):
            with self.assertRaises(Exception):
                select(dict(self.request(), **changes))

    def test_prepare_uses_exact_bundle_and_selected_camera(self):
        bundle=object()
        with patch('autospine_workbench.targets.character43.source_ankle_targets.extract',return_value={'ready':True}) as extract:
            self.assertIsNone(prepare(bundle,{}));extract.assert_not_called()
            self.assertEqual(prepare(bundle,self.request(projection={'yaw_degrees':-30})),{'ready':True})
            extract.assert_called_once_with(bundle,-30)

    def test_comparisons_separate_strategies_without_changing_legacy_identity(self):
        manager=SimpleNamespace(get=lambda _:dict(source_sha256='a',format='bvh'))
        old=signature(manager,{'source_job_id':'source','contact_correction':False})
        new=signature(manager,dict(self.request(),source_job_id='source'))
        self.assertNotIn('moving_ankle_profile',old)
        self.assertNotEqual(old,new)
        self.assertEqual(new['moving_ankle_profile'],PROFILE)

    def test_worker_extracts_persisted_source_and_captures_new_candidate(self):
        import json
        import tempfile
        from pathlib import Path
        from autospine_workbench.automation.motion_intake_worker import compile_source
        from autospine_workbench.automation.motion_target_worker import execute
        from autospine_workbench.automation.animated_store import AnimatedStore
        from autospine_workbench.automation.storage_io import canonical_bytes
        from tests.test_motion_target_intake import inputs
        from tests.test_mixamo_map import source
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); intake=root/'intake'; target=root/'target'
            intake.mkdir();target.mkdir()
            raw=source();(intake/'source.bvh').write_bytes(raw)
            identity=compile_source(raw,'front',intake,root)['motion']
            files=inputs()[0];doc=json.loads(files['skeleton.json'])
            for name,parent in [('spine','root'),('chest','spine'),('neck','chest')]:
                doc['bones'].append(dict(name=name,parent=parent,x=0,y=10,rotation=0))
            files['skeleton.json']=canonical_bytes(doc)
            store=AnimatedStore(root); original=store.publish(files)
            request=dict(self.request(),motion_identity=identity,character_sha256=original)
            (target/'request.json').write_bytes(canonical_bytes(request))
            with patch('autospine_workbench.automation.motion_target_worker.capture',return_value={'status':'unavailable'}) as capture:
                execute(target,root,root)
            result=json.loads((target/'worker-result.json').read_bytes())
            self.assertEqual(result['moving_ankle_profile'],PROFILE)
            output=store.read(result['artifact_sha256'])
            evidence=json.loads(output['motion-moving-ankles.json'])
            self.assertEqual(evidence['source_observation']['source_bundle_sha256'],identity['bundle_sha256'])
            self.assertEqual(store.read(original),files)
            capture.assert_called_once()
            self.assertEqual(result['runtime']['status'],'unavailable')

    def test_submission_persists_strategy_for_retries(self):
        import json
        import tempfile
        from pathlib import Path
        from threading import RLock
        from unittest.mock import Mock
        from autospine_workbench.automation.motion_target_jobs import submit
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source=dict(status='succeeded',name='source',result=dict(motion_status='compiled',motion={}))
            characters=SimpleNamespace(verified_snapshot=lambda *args:({'artifact_sha256':'a'*64},{}))
            def folder(job, create=False):
                path=root/job
                if create:
                    (path/'staging').mkdir(parents=True)
                return path
            manager=SimpleNamespace(get=lambda _:source,character_manager=lambda:characters,
                folder=folder,_lock=RLock(),_closed=False,_jobs={},_cancel={},
                _pool=Mock(),_execute=Mock())
            with patch('autospine_workbench.automation.motion_target_jobs.assert_current'):
                job=submit(manager,'source',dict(self.request(),project_id='alice',character_job_id='character'))
            saved=json.loads((root/job['job_id']/'request.json').read_bytes())
            self.assertEqual(saved['moving_ankle_profile'],PROFILE)
            self.assertFalse(saved['contact_correction'])
            manager._pool.submit.assert_called_once()
