from copy import deepcopy
import unittest
from unittest.mock import patch
from autospine_workbench.automation.motion_moving_ankles import check
from autospine_workbench.targets.character43.final_motion_contact import recheck
from tests import test_motion_moving_ankles as fixtures
from autospine_workbench.automation.motion_moving_ankles import apply


class ContactEndRoundingTests(unittest.TestCase):
    def test_rounding_keeps_actual_times_but_rejects_cropped_or_extended_clip(self):
        doc,motion,obs=fixtures.MovingAnkleStageTests().prepared()
        candidate,report=apply(doc,'move',motion,obs,[0,1,2],20,bundle_sha256='b'*64)
        times=[0,1,2.000000032]
        before=deepcopy(times)
        result=check(candidate,'move',report,times,20)
        self.assertEqual(result['samples'],3)
        with patch('autospine_workbench.targets.character43.final_motion_contact.analyze',
                   return_value={'passed':True}) as analyze:
            contact=recheck(candidate,'move',motion,{},times,20)
            self.assertEqual(analyze.call_args.args[3],times)
            self.assertEqual(contact['final_timeline_check']['samples'],3)
        self.assertEqual(times,before)
        for end in (1.99,2.00001,float('nan')):
            with self.assertRaises(ValueError):check(candidate,'move',report,[0,1,end],20)
            with self.assertRaises(ValueError):recheck(candidate,'move',motion,{},[0,1,end],20)
