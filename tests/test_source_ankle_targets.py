from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.source_ankle_targets import targets


class SourceAnkleTargetsTests(unittest.TestCase):
    def fixture(self):
        return dict(times=[0, 1, 2], source_reference_length=10,
                    points=[[[1, 2, 3], [4, 5, 6]], [[1, 2, 3], [5, 6, 7]],
                            [[2, 1, 3], [6, 7, 8]]])

    def test_initial_placement_preserved_moving_foot_not_locked(self):
        observation = self.fixture(); before = deepcopy(observation)
        rows = targets(observation, [[100, -100], [200, -200]], 100)
        self.assertEqual(rows[0]['targets'], [[100, -100], [200, -200]])
        self.assertEqual(rows[1]['targets'], [[100, -100], [210, -210]])
        self.assertEqual(rows[2]['targets'], [[110, -90], [220, -220]])
        self.assertEqual(observation, before)

    def test_scale_covariance(self):
        for scale in (.1, 2, 10):
            base = targets(self.fixture(), [[0, 0], [0, 0]], 100)
            scaled = targets(self.fixture(), [[0, 0], [0, 0]], 100*scale)
            for a, b in zip(base, scaled):
                for p, q in zip(a['targets'], b['targets']):
                    self.assertEqual([v*scale for v in p], q)

    def test_invalid_reference_or_nonfull_timebase_rejected(self):
        for change in ({'times':[1, 2, 3]}, {'times':[0, 1, 1]},
                       {'source_reference_length':0}, {'points':[]}):
            with self.assertRaisesRegex(ValueError, 'source_observations_invalid'):
                targets(dict(self.fixture(), **change), [[0, 0], [0, 0]], 100)
