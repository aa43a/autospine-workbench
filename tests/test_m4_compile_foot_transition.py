import unittest
from m4_compile_foot_transition import runtime_keys


class FootBakeKeyTests(unittest.TestCase):
    def test_equal_keys_at_same_runtime_time_are_merged(self):
        keys=[dict(time=1.,vertices=[2.]),dict(time=1.+1e-9,vertices=[2.])]
        result,report=runtime_keys(keys)
        self.assertEqual(result,[dict(time=1.,vertices=[2.])])
        self.assertEqual(report['merged_keys'],1)

    def test_conflicting_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicting_float32'):
            runtime_keys([dict(time=1.,vertices=[2.]),dict(time=1.+1e-9,vertices=[3.])])
