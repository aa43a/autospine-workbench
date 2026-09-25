from copy import deepcopy
import unittest
from autospine_workbench.automation.motion_contact_issues import reconcile
from autospine_workbench.resolved_project import canonical_sha256


class ContactIssueTests(unittest.TestCase):
    def test_exact_final_pass_archives_only_superseded_drift(self):
        doc={'animations':{}}
        issues=[dict(stage='contact',reason_code='motion_inferred_contact_drift'),
                dict(stage='contact',reason_code='motion_source_contact_intervals_unverified'),
                dict(stage='contact',reason_code='motion_moving_ankle_infeasible'),
                dict(stage='geometry',reason_code='motion_target_deformation_needs_changes')]
        original=deepcopy(issues)
        contact=dict(after=dict(passed=True),final_timeline_check=dict(skeleton_sha256=canonical_sha256(doc)))
        active,resolved=reconcile(issues,contact,doc)
        self.assertEqual(active,issues[1:]);self.assertEqual(len(resolved),1)
        self.assertEqual(resolved[0]['reason_code'],issues[0]['reason_code'])
        self.assertEqual(issues,original)
        for passed in (False,None):
            contact['after']['passed']=passed
            self.assertEqual(reconcile(issues,contact,doc),(issues,[]))
        contact['final_timeline_check']['skeleton_sha256']='stale'
        with self.assertRaisesRegex(ValueError,'identity'):reconcile(issues,contact,doc)


if __name__=='__main__':unittest.main()
