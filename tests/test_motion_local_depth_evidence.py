from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_local_depth_evidence import publish,read


class EvidenceTests(unittest.TestCase):
    def test_exact_identity_missing_and_idempotent_history(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'job';folder.mkdir()
            files={'skeleton.json':b'{}'};artifact=AnimatedStore(root).publish(files)
            request=dict(job_id='motion-test',source='one')
            self.assertEqual(read(root,folder,request,artifact,files)['reports'],[])
            report=dict(job_id=request['job_id'],artifact_sha256=artifact,authority='none',selected=False,
                        records=[],profile='test',interpolation='source_samples_only')
            digest=publish(root,folder,request,artifact,report)
            self.assertEqual(publish(root,folder,request,artifact,report),digest)
            self.assertEqual(len(read(root,folder,request,artifact,files)['reports']),1)
            with self.assertRaisesRegex(ValueError,'stale'):
                read(root,folder,dict(request,source='two'),artifact,files)
            with self.assertRaisesRegex(ValueError,'stale'):
                read(root,folder,request,artifact,{'skeleton.json':b'changed'})
            with self.assertRaisesRegex(ValueError,'report_identity'):
                publish(root,folder,request,artifact,dict(report,selected=True))
            records=[dict(pair=['a','b'],check=dict(time=t,status='requires_partition_or_more_depth',
                counts=dict(front=0,back=0,ambiguous=1,unknown=0),overlap_pixels=1)) for t in range(25)]
            records.append(dict(pair=['a','b'],check=dict(time=25,status='unmeasured',reason_code='budget')))
            publish(root,folder,request,artifact,dict(report,records=records))
            latest=next(r for r in read(root,folder,request,artifact,files)['reports'] if r['records'])
            self.assertEqual(len(latest['records']),21)
            self.assertEqual(latest['records'][-1]['status'],'unmeasured')


if __name__=='__main__':unittest.main()
