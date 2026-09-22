from copy import deepcopy
import math
import unittest
import numpy as np
from autospine_workbench.targets.spine43.deform_storage import compact


def document(values):
    return dict(bones=[dict(name='root', x=.1234567890123)], animations={'move':dict(attachments={
        'default':{'clip':{'clip':{'deform':[dict(time=.1234567890123, offset=2, curve='stepped', vertices=values)]}}}})})


class DeformStorageTests(unittest.TestCase):
    def test_only_deform_values_change_and_float32_bits_match(self):
        values = [.1234567890123, -35.1234567890123, 0., -0., 1e-39, 1e-44, 12345678.25]
        doc = document(values); original = deepcopy(doc)
        result, report = compact(doc)
        frame = result['animations']['move']['attachments']['default']['clip']['clip']['deform'][0]
        self.assertEqual(np.asarray(frame['vertices'], dtype=np.float32).tobytes(), np.asarray(values, dtype=np.float32).tobytes())
        self.assertEqual(math.copysign(1, frame['vertices'][3]), -1)
        self.assertEqual(result['bones'], original['bones'])
        self.assertEqual(frame['time'], .1234567890123);self.assertEqual(frame['offset'], 2)
        self.assertEqual(frame['curve'], 'stepped');self.assertEqual(doc, original)
        self.assertGreater(report['changed_values'], 0)
        self.assertEqual(compact(result)[0], result)

    def test_rejects_nonfinite_and_float32_overflow(self):
        for value in [float('nan'), float('inf'), 1e100, True, '1.0']:
            with self.assertRaises(ValueError): compact(document([value]))

    def test_random_import_equivalence(self):
        random = np.random.default_rng(4)
        values = (random.normal(size=3000)*10**random.uniform(-30, 30, 3000)).tolist()
        result, _ = compact(document(values))
        actual = result['animations']['move']['attachments']['default']['clip']['clip']['deform'][0]['vertices']
        self.assertEqual(np.array(actual, dtype=np.float32).tobytes(), np.array(values, dtype=np.float32).tobytes())
