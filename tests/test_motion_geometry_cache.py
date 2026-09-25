import json
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from autospine_workbench.automation.motion_geometry_cache import GeometryCache
from autospine_workbench.automation.motion_target_jobs import review_file

MODULE = 'autospine_workbench.automation.motion_geometry_cache'


class GeometryCacheTests(unittest.TestCase):
    def test_concurrent_hits_keep_exact_bytes_and_do_not_recompute(self):
        cache = GeometryCache()
        value = dict(artifact_sha256='a', status='needs_changes', rows=[{'failed': True}])
        with patch(MODULE + '.build', return_value=value) as build:
            with ThreadPoolExecutor(4) as pool:
                rows = list(pool.map(lambda _: cache.read({}, 'a'), range(8)))
            self.assertEqual(build.call_count, 1)
        self.assertTrue(all(raw == rows[0] for raw in rows))
        self.assertEqual(json.loads(rows[0]), value)
        value['rows'].clear()
        self.assertEqual(json.loads(cache.read({}, 'a'))['rows'], [{'failed': True}])

    def test_new_artifact_and_lru_eviction_recompute(self):
        cache = GeometryCache(entries=2)
        with patch(MODULE + '.build', side_effect=lambda _, a: dict(artifact_sha256=a)) as build:
            for key in ('a', 'b', 'a', 'c', 'b'):
                self.assertEqual(json.loads(cache.read({}, key))['artifact_sha256'], key)
            self.assertEqual(build.call_count, 4)

    def test_failure_and_oversize_are_not_cached(self):
        cache = GeometryCache(max_bytes=1)
        with patch(MODULE + '.build', side_effect=[ValueError('failed'),
                dict(artifact_sha256='a'), dict(artifact_sha256='a')]) as build:
            with self.assertRaisesRegex(ValueError, 'failed'):
                cache.read({}, 'a')
            self.assertEqual(cache.read({}, 'a'), cache.read({}, 'a'))
            self.assertEqual(build.call_count, 3)

    def test_wrong_identity_is_never_cached(self):
        with patch(MODULE + '.build', return_value=dict(artifact_sha256='b')):
            with self.assertRaisesRegex(ValueError, 'cache_identity'):
                GeometryCache().read({}, 'a')

    def test_total_byte_budget_evicts_even_below_entry_limit(self):
        size = len(json.dumps(dict(artifact_sha256='a')).encode())
        cache = GeometryCache(entries=10, max_bytes=size*2)
        with patch(MODULE + '.build', side_effect=lambda _, a: dict(artifact_sha256=a)) as build:
            for key in ('a', 'b', 'c', 'a'):
                cache.read({}, key)
            self.assertEqual(build.call_count, 4)

    def test_route_verifies_current_source_before_every_cache_access(self):
        with (patch('autospine_workbench.automation.motion_target_jobs.context',
                    side_effect=[({'artifact_sha256': 'a'}, {}), ValueError('stale_source')]) as context,
              patch(MODULE + '.read', return_value=b'{}') as cached):
            self.assertEqual(review_file(None, 'job', ['geometry-details.json']), (b'{}', 'application/json'))
            with self.assertRaisesRegex(ValueError, 'stale_source'):
                review_file(None, 'job', ['geometry-details.json'])
            self.assertEqual(context.call_count, 2)
            self.assertEqual(cached.call_count, 1)
