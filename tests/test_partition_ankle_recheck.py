from copy import deepcopy
import json
import unittest
from test_motion_moving_ankles import MovingAnkleStageTests
from autospine_workbench.automation.motion_moving_ankles import apply, check
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.partition_ankle_recheck import apply as recheck


class PartitionAnkleTests(unittest.TestCase):
    def fixture(self):
        doc,motion,obs=MovingAnkleStageTests().prepared()
        doc,report=apply(doc,'move',motion,obs,[0,1,2],20,bundle_sha256='b'*64)
        report['final_check']=check(doc,'move',report,[0,1,2],20)
        return doc,{'skeleton.json':canonical_bytes(doc),'motion-moving-ankles.json':canonical_bytes(report)}

    def test_fresh_measurement_and_failure_retention(self):
        doc,files=self.fixture();before=deepcopy(files)
        for changed in (False,True):
            candidate=deepcopy(doc)
            if changed:candidate['animations']['move']['bones']['root']['translate'][-1]['x']+=10
            output={};evidence={'reference_length_px':20,'issues':[]}
            recheck(files,output,candidate,'move',[0,.5,1,1.5,2],evidence)
            measured=json.loads(output['motion-moving-ankles.json'])
            self.assertEqual(measured['final_check']['passed'],not changed)
            self.assertEqual(measured['final_check']['samples'],5)
            self.assertTrue(measured['parent_final_check']['passed'])
            self.assertEqual(bool(evidence['issues']),changed)
        self.assertEqual(files,before)

    def test_missing_not_fabricated_stale_rejected(self):
        doc,files=self.fixture();output={};evidence={'reference_length_px':20}
        recheck({},output,doc,'move',[0,2],evidence)
        self.assertEqual(output,{})
        files['skeleton.json']+=b' '
        with self.assertRaisesRegex(ValueError,'source_identity'):
            recheck(files,output,doc,'move',[0,2],evidence)


if __name__=='__main__':unittest.main()
