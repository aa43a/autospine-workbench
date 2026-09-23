import json
from hashlib import sha256
import unittest
from autospine_workbench.automation.motion_repair_lineage import carry


class RepairLineageTests(unittest.TestCase):
    def test_chain_keeps_exact_prior_decisions(self):
        raw=b'{"profile":"partition","selected":false}'
        source={'motion-repair-provenance.json':raw,'motion-repair.json':b'{"geometry":{"passed":false}}'}
        repair=dict(parent_repair_sha256=sha256(raw).hexdigest(),parent_artifact_sha256='a'*64,parent_job_id='parent')
        first=carry(source,repair);record=json.loads(next(iter(first.values())))
        self.assertFalse(record['report']['geometry']['passed']);self.assertFalse(record['selected'])
        second=carry(dict(source,**first),dict(repair,parent_job_id='child',parent_artifact_sha256='b'*64))
        self.assertEqual(len(second),2)
        for key,value in first.items():self.assertEqual(second[key],value)

    def test_stale_missing_and_corrupt_parent_rejected(self):
        with self.assertRaisesRegex(ValueError,'missing'):carry({},dict(parent_repair_sha256='a'*64))
        with self.assertRaisesRegex(ValueError,'changed'):carry({'motion-repair-provenance.json':b'{}'}, {})
        raw=b'{}';source={'motion-repair-provenance.json':raw,'repair-history/wrong.json':b'{}'}
        with self.assertRaisesRegex(ValueError,'identity'):carry(source,dict(parent_repair_sha256=sha256(raw).hexdigest()))
        self.assertEqual(carry({},{}),{})
