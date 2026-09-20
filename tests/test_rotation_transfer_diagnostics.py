import unittest
from autospine_workbench.targets.character43.rotation_transfer_diagnostics import compare


class TransferTests(unittest.TestCase):
    def run_case(self, source, target):
        role = 'humanoid.arm.upper.left'
        motion = dict(ticks_per_second=1, tracks=[dict(target=role, property='rotation', interpolation='linear',
            keys=[dict(tick=i, value=-v) for i,v in enumerate(source)])])
        skeleton = {'animations': {'test': {'bones': {'upperarm_l': {'rotate': [
            dict(time=i,value=v) for i,v in enumerate(target)]}}}}}
        diagnostic = {'records': [dict(role=role, events=[dict(time=1,reason='angle_branch_crossing')])]}
        return compare(motion,skeleton,'test',diagnostic)['records'][0]

    def test_actual_two_turns_are_preserved_without_false_extra_turn(self):
        row=self.run_case([0,180,360,540,720],[0,180,360,540,720])
        self.assertFalse(row['extra_turn_suspected'])
        self.assertEqual(row['maximum_transfer_difference_deg'],0)

    def test_extra_turn_is_not_hidden_by_modulo(self):
        row=self.run_case([0,1,2],[0,361,362])
        self.assertTrue(row['extra_turn_suspected'])
        self.assertEqual(row['large_key_intervals'][0]['delta_deg'],361)

    def test_bounded_correction_is_reported_not_called_extra_turn(self):
        row=self.run_case([0,10,20],[0,20,20])
        self.assertFalse(row['extra_turn_suspected'])
        self.assertEqual(row['maximum_difference_time'],1)
        self.assertEqual(row['maximum_transfer_difference_deg'],10)

    def test_time_range_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'time_range'):
            self.run_case([0,1,2],[0,1])


if __name__ == '__main__': unittest.main()
