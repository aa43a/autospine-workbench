from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from m4_local_depth_matrix import run,PROFILE
from m4_motion_cohort import digest


class MatrixTests(unittest.TestCase):
    def test_resume_verifies_checkpoint_bytes_before_reusing_results(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);plan={'motions':[{'id':'walk'}],'characters':[{'id':'a'}]}
            cohort={'plan_sha256':digest(plan),'cells':{'walk/a':{'job_id':'j','result':{'artifact_sha256':'asset'}}}}
            p=root/'plan.json';c=root/'cohort.json';out=root/'out';out.mkdir()
            p.write_text(json.dumps(plan));c.write_text(json.dumps(cohort))
            (out/'report.json').write_bytes(b'original')
            state=dict(identity=dict(plan_sha256=digest(plan),cohort_sha256=sha256(c.read_bytes()).hexdigest(),profile=PROFILE),
                cells={'walk/a':dict(artifact_sha256='asset',file='report.json',report_sha256=sha256(b'original').hexdigest())})
            (out/'state.json').write_text(json.dumps(state))
            with patch('m4_local_depth_matrix.api',side_effect=AssertionError('must reuse exact completed result')):
                self.assertEqual(run(p,c,out,1),state)
                (out/'report.json').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'checkpoint_changed'):run(p,c,out,1)
            state['identity']['profile']='different'
            (out/'state.json').write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError,'resume_identity'):run(p,c,out,1)


if __name__=='__main__':unittest.main()
