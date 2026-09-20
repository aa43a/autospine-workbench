from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from tempfile import TemporaryDirectory
from pathlib import Path
from hashlib import sha256

from autospine_workbench.automation.motion_view_comparison import compare, LIMBS
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.mixamo_map import build_map
from test_mixamo_map import source
from autospine_workbench.automation.motion_reproject import submit
from autospine_workbench.automation.storage_io import publish_document


class ViewComparisonTests(unittest.TestCase):
    def setUp(self):
        self.bundle = SimpleNamespace(source_kind='bvh', raw_bvh=source())
        self.mapping = build_map(parse_bvh(source()), clip_id='view', reference_length=10,
                                 screen_x='+X', screen_y='-Y', depth='+Z')

    def test_real_bvh_bases_and_mapping_are_preserved(self):
        original = deepcopy(self.mapping)
        result = compare(self.bundle, self.mapping, 'front')
        self.assertEqual(self.mapping, original)
        self.assertEqual([r['view'] for r in result['records']], ['front', 'side'])
        self.assertTrue(all(len(r['diagnostic']['records']) == 8 for r in result['records']))
        self.assertEqual(result['authority'], 'none')

    def run_views(self, front, side, current='front', roles=LIMBS):
        def series(_, mapping):
            values = front if mapping['basis']['screen_x'] == '+X' else side
            return {role: values for role in roles}, [0, 1]
        with patch('autospine_workbench.automation.motion_view_comparison.bvh_series', side_effect=series):
            return compare(self.bundle, self.mapping, current)

    def test_no_least_bad_auto_adoption_and_preserve_passing_user_view(self):
        self.assertIsNone(self.run_views([.1, .1], [.15, .15])['recommended_view'])
        self.assertEqual(self.run_views([.1, .1], [.8, .8])['recommended_view'], 'side')
        self.assertEqual(self.run_views([.8, .8], [.9, .9], 'front')['recommended_view'], 'front')
        self.assertEqual(self.run_views([.8, .8], [.9, .9], 'side')['recommended_view'], 'side')
        self.assertIsNone(self.run_views([.8, .8], [.9, .9], roles={'humanoid.arm.upper.left'})['recommended_view'])

    def test_auto_selection_is_revalidated_and_recorded_before_upload(self):
        with TemporaryDirectory() as temp:
            root = Path(temp); raw = source(); (root/'source.bvh').write_bytes(raw)
            publish_document(root/'request.json', {}, staging=root/'staging')
            manager = SimpleNamespace(folder=lambda _:root, upload=Mock(return_value={'job_id': 'new'}),
                get=lambda _:dict(status='succeeded', format='bvh', source_sha256=sha256(raw).hexdigest(), name='source'))
            comparison = dict(profile='profile', comparison_sha256='exact', recommended_view='side')
            with patch('autospine_workbench.automation.motion_view_comparison.inspect', return_value=comparison):
                for body in (dict(view='side', comparison_sha256='old'), dict(view='front', comparison_sha256='exact')):
                    with self.assertRaisesRegex(RuntimeError, 'comparison_changed'):
                        submit(manager, 'source', body)
                manager.upload.assert_not_called()
                submit(manager, 'source', dict(view='side', comparison_sha256='exact'))
                self.assertEqual(manager.upload.call_args.kwargs['derivation']['comparison_sha256'], 'exact')
                self.assertEqual(manager.upload.call_args.args[0].getvalue(), raw)


if __name__ == '__main__': unittest.main()
