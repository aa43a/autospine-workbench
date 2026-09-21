from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from m4_local_depth_matrix_audit import audit
from m4_motion_cohort import digest
from autospine_workbench.targets.character43.local_depth_summary import summarize


class MatrixAuditTests(unittest.TestCase):
    def test_processed_unmeasured_and_pending_are_distinct(self):
        with TemporaryDirectory() as temp:
            folder=Path(temp)
            plan=dict(motions=[dict(id='walk'),dict(id='turn')],characters=[dict(id='a')])
            report=dict(job_id='job',artifact_sha256='asset',records=[dict(pair=['arm','body'],
                check=dict(time=0,status='unmeasured',reason_code='budget'))],counts={'unmeasured':1})
            raw=json.dumps(report).encode();(folder/'report.json').write_bytes(raw)
            state=dict(identity=dict(plan_sha256=digest(plan)),cells={'walk/a':dict(file='report.json',job_id='job',
                report_sha256=sha256(raw).hexdigest(),artifact_sha256='asset',counts=report['counts'],causes=summarize(report['records']))})
            cohort=dict(plan_sha256=digest(plan),cells={'walk/a':dict(job_id='job',result=dict(
                artifact_sha256='asset',geometry_passed=True,runtime=dict(frames=7),contact_status='not_checked'))})
            result=audit(plan,cohort,state,folder)
            self.assertEqual((result['processed'],result['pending'],result['fully_measured'],result['incomplete']),(1,1,0,1))
            self.assertFalse(result['selected'])
            report['records']=[];report['counts']={}
            raw=json.dumps(report).encode();(folder/'report.json').write_bytes(raw)
            state['cells']['walk/a'].update(report_sha256=sha256(raw).hexdigest(),counts={},causes=summarize([]))
            result=audit(plan,cohort,state,folder)
            self.assertEqual((result['fully_measured'],result['incomplete']),(0,1))
            (folder/'report.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'report_changed'):audit(plan,cohort,state,folder)


if __name__=='__main__':unittest.main()
