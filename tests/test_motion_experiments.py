import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import publish_document
from autospine_workbench.automation.motion_experiments import publish, load, entries, validate


class ExperimentTests(unittest.TestCase):
    def test_registration_is_idempotent_and_rejects_changed_baseline(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'job';folder.mkdir()
            files={'skeleton.json':b'{}'};address=AnimatedStore(root).publish(files)
            request=dict(job_id='test',character_sha256='character',motion_identity={'clip':'source'})
            parent=dict(job_id='test',source_character_sha256='character',motion_identity={'clip':'source'},candidate_bundle_sha256='parent')
            report=dict(profile='post-contact-source-pose-repair-v1',source_candidate_sha256='parent',
                candidate_bundle_sha256=address,authority='none',selected=False,production_authorized=False,sampled_frames=1)
            runtime=dict(bundle_sha256=address,results=[{'time':0}])
            publish_document(folder/'request.json',request,staging=folder/'staging')
            digest=publish(root,folder,request,'baseline',parent,report,runtime,files)
            self.assertEqual(publish(root,folder,request,'baseline',parent,report,runtime,files),digest)
            self.assertEqual(entries(folder),[digest])
            manager=SimpleNamespace(state_root=root,folder=lambda _:folder,get=lambda _:dict(result=dict(artifact_sha256='baseline')))
            self.assertEqual(load(manager,'test',digest)['report'],report)
            manager.get=lambda _:dict(result=dict(artifact_sha256='changed'))
            with self.assertRaisesRegex(ValueError,'baseline_changed'):load(manager,'test',digest)
            for bad in [dict(report,selected=True),dict(report,source_candidate_sha256='wrong')]:
                with self.assertRaisesRegex(ValueError,'parent_mismatch'):validate(request,parent,bad,runtime)
            with self.assertRaisesRegex(ValueError,'runtime_mismatch'):validate(request,parent,report,dict(runtime,bundle_sha256='wrong'))
            with self.assertRaisesRegex(ValueError,'source_mismatch'):validate(dict(request,clip={'start':1}),parent,report,runtime)
            with self.assertRaisesRegex(ValueError,'candidate_mismatch'):
                publish(root,folder,request,'baseline',parent,report,runtime,{'skeleton.json':b'changed'})
            with self.assertRaisesRegex(ValueError,'unregistered'):load(manager,'test','../elsewhere')


if __name__=='__main__':unittest.main()
