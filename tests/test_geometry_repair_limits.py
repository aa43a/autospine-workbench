import unittest
from hashlib import sha256
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.geometry_repair_limits import annotate


class RepairLimitTests(unittest.TestCase):
    def test_fixed_area_counterexample_preserves_failed_gate_and_identity(self):
        setup={'leg':[[0,0],[1,0],[0,1]]}
        doc=dict(skins=[dict(attachments={'leg':{'leg':dict(triangles=[0,1,2],
            vertices=[1,0,0,0,1,1,0,1,0,1,1,0,0,1,1])}})],animations={'a':{}})
        raw=canonical_bytes(doc);digest=sha256(raw).hexdigest()
        files={'skeleton.json':raw,'numeric-reference.json':canonical_bytes(dict(skeleton_sha256=digest,
            animations={'a':[dict(time=0,vertices=setup),dict(time=1,vertices={'leg':[[0,0],[1,0],[0,.3]]})]}))}
        qa=dict(skeleton_sha256=digest,passed=False,records=[dict(slot='leg',animation='a',passed=False)])
        result=annotate(files,qa,setup)
        limit=result['records'][0]['repair_limit']
        self.assertEqual(limit['triangle_count'],1);self.assertEqual(limit['first']['time'],1)
        self.assertFalse(result['passed']);self.assertNotIn('repair_limit',qa['records'][0])
        self.assertEqual(annotate(files,qa,None),qa)
        with self.assertRaisesRegex(ValueError,'identity'):annotate(files,dict(qa,skeleton_sha256='old'),setup)


if __name__=='__main__':unittest.main()
