from copy import deepcopy
import unittest

from test_motion_depth_overlap import fixture
from autospine_workbench.targets.character43.motion_depth_overlap import Probe


class VisibilityTests(unittest.TestCase):
    def test_hidden_setup_slot_stays_hidden_until_first_key(self):
        doc, files = fixture()
        doc['slots'][0]['color'] = 'ffffff00'
        doc['animations']['test']['slots'] = {'a': {'alpha': [dict(time=1, value=1, curve='stepped')]}}
        probe = Probe(doc, files, 'test')
        self.assertEqual(probe.pair('a', 'b', 0)['overlap_pixels'], 0)
        self.assertEqual(probe.pair('a', 'b', 1)['overlap_pixels'], 4)

    def test_switch_boundaries_and_tiled_cache_match_visible_texture(self):
        doc, files = fixture()
        doc['animations']['test']['slots'] = {'a': {'alpha': [
            dict(time=1, value=0, curve='stepped'),
            dict(time=2, value=1, curve='stepped')]}}
        original = deepcopy(doc)
        for tiled in (False, True):
            probe = Probe(doc, files, 'test', tiled=tiled)
            for time, count in ((0, 4), (.9999, 4), (1, 0), (1.9999, 0), (2, 4)):
                self.assertEqual(probe.pair('a', 'b', time)['overlap_pixels'], count)
                self.assertEqual(probe.pair('b', 'a', time)['overlap_pixels'], count)
                if tiled:
                    self.assertEqual(int(probe.cached_common('a', 'b', time, [0, -2, 2, 2]).sum()), count)
        self.assertEqual(doc, original)

    def test_unsupported_and_malformed_tracks_are_not_reported_as_clear(self):
        invalid = [[], [dict(value=.5, curve='stepped')], [dict(value=0)],
            [dict(time=-1, value=0, curve='stepped')],
            [dict(time=float('nan'), value=0, curve='stepped')],
            [dict(value=0, curve='stepped'), dict(value=1, curve='stepped')]]
        for keys in invalid:
            doc, files = fixture()
            doc['animations']['test']['slots'] = {'a': {'alpha': keys}}
            with self.assertRaisesRegex(ValueError, 'attachment_unsupported'):
                Probe(doc, files, 'test').pair('a', 'b', 0)
        doc, files = fixture()
        doc['animations']['test']['slots'] = {'a': {'attachment': []}}
        with self.assertRaisesRegex(ValueError, 'attachment_unsupported'):
            Probe(doc, files, 'test').pair('a', 'b', 0)


if __name__ == '__main__':
    unittest.main()
