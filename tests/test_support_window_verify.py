from copy import deepcopy
import unittest
from test_support_timeline import fixture
from m4_support_window_verify import verify
from autospine_workbench.targets.character43.motion_contacts import schedule


class WindowVerificationTests(unittest.TestCase):
    def values(self):
        doc,motion=fixture();names=('thigh_l','calf_l','thigh_r','calf_r')
        for n in names:doc['animations']['walk']['bones'][n]={'rotate':[dict(time=0,value=0)]}
        doc['animations']['external-motion']=doc['animations'].pop('walk')
        rows=[dict(time=t,root_shift=[0,0],angles={n:0 for n in names}) for t in (0,.4,.8,1.2)]
        contact=dict(phase_attempt=dict(rows=rows),hypothesis=dict(ticks_per_second=motion['ticks_per_second'],markers=motion['markers']))
        pose=dict(times=[0,1.2],vectors={'humanoid.leg.upper.left':[(0,1,0),(0,1,0)]})
        return doc,motion,pose,contact,dict(candidate_rows=rows)

    def test_shared_grid_includes_feedback_exactly_without_recursive_expansion(self):
        doc,motion,pose,contact,report=self.values()
        times=schedule(motion,[r['time'] for r in report['candidate_rows']])
        report['verification_time_grid']=sorted(set(times)|{.123})
        original=deepcopy(report)
        result=verify(doc,doc,motion,pose,contact,report,20)
        self.assertEqual(result['contact_after']['samples'],len(report['verification_time_grid']))
        self.assertEqual(report,original)

    def test_missing_original_contact_boundary_is_rejected(self):
        doc,motion,pose,contact,report=self.values();report['verification_time_grid']=[0,1.2]
        with self.assertRaisesRegex(ValueError,'explicit_grid_invalid'):
            verify(doc,doc,motion,pose,contact,report,20)

    def test_duplicate_replacement_time_is_rejected(self):
        doc,motion,pose,contact,report=self.values();report['candidate_rows'].append(deepcopy(report['candidate_rows'][0]))
        with self.assertRaisesRegex(ValueError,'replacement_times_invalid'):
            verify(doc,doc,motion,pose,contact,report,20)
