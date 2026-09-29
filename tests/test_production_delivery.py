from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import time

from autospine_workbench.automation.production_delivery import ProductionDeliveries
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.animated_store import AnimatedStore
from test_multi_animation import source


class DeliveryTests(TestCase):
    def test_durable_result_exact_sources_and_reject_stale_download(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = AnimatedStore(root)
            fixtures = [source('a'), source('b', 35)]
            for fixture in fixtures:
                self.assertEqual(store.publish(fixture['files']), fixture['artifact_sha256'])
            rows = {f'run-{i}': dict(request=dict(project_id='alice'), stages=dict(joint=dict(
                status='succeeded', job_id=f'joint-{i}', artifact_sha256=f['artifact_sha256'])))
                for i, f in enumerate(fixtures)}
            projects = SimpleNamespace(state_root=root, workspace_root=root)
            production = SimpleNamespace(journal=SimpleNamespace(root=root/'jobs/production-v1'),
                driver=SimpleNamespace(motions=SimpleNamespace(projects=projects), validate=lambda request: None),
                get=lambda run: deepcopy(rows[run]))
            def context(manager, job):
                item = fixtures[int(job[-1])]
                return dict(artifact_sha256=item['artifact_sha256']), item['files']
            calls = []
            def capture(projects, store, digest, output, **kwargs):
                calls.append(digest)
                raw = canonical_bytes(dict(bundle_sha256=digest, authority='none', production_authorized=False))
                (output/'runtime').mkdir()
                (output/'runtime/report.json').write_bytes(raw)
                return dict(status='needs_review', frames=6, geometry_status='passed',
                            files={'report.json': sha256(raw).hexdigest()})
            with patch('autospine_workbench.automation.production_delivery.context', side_effect=context), \
                    patch('autospine_workbench.automation.production_delivery.capture', side_effect=capture):
                manager = ProductionDeliveries(production)
                try:
                    job = manager.submit(dict(run_ids=list(rows)))['job_id']
                    deadline = time.monotonic()+5
                    while manager.get(job)['status'] in ('pending', 'running') and time.monotonic()<deadline:
                        time.sleep(.01)
                    value = manager.get(job)
                    self.assertEqual(value['status'], 'needs_review', value)
                    self.assertEqual(value['visual_status'], 'not_reviewed')
                    self.assertTrue(manager.download(job).startswith(b'PK'))
                    raw, mime = manager.review_file(job, ['report.json'])
                    self.assertEqual(mime, 'application/json')
                    self.assertIn(value['artifact_sha256'].encode(), raw)
                    for parts in (['..', 'report.json'], ['missing.png'], ['a\\report.json']):
                        with self.assertRaisesRegex(RuntimeError, 'pipeline_artifact_not_found'):
                            manager.review_file(job, parts)
                    report_path = manager.folder(job)/value['attempt']/'runtime/report.json'
                    report_path.write_bytes(b'changed')
                    with self.assertRaisesRegex(RuntimeError, 'production_delivery_report_changed'):
                        manager.review_file(job, ['report.json'])
                    report_path.write_bytes(raw)
                    self.assertEqual(manager.submit(dict(run_ids=list(rows)))['job_id'], job)
                    self.assertEqual(len(calls), 1)
                    with self.assertRaisesRegex(RuntimeError, 'conflict'):
                        manager.review(job, dict(expected_revision=0, verdict='stage_accepted', notes=''))
                    value = manager.review(job, dict(expected_revision=value['revision'],
                        verdict='needs_changes', notes='test-only observation'))
                    self.assertEqual(value['visual_status'], 'needs_changes')
                    self.assertFalse(value['production_authorized'])
                    rows['run-1']['stages']['joint']['artifact_sha256'] = '0'*64
                    with self.assertRaisesRegex(RuntimeError, 'production_completed_child_changed'):
                        manager.download(job)
                finally:
                    manager.close()
                reopened = ProductionDeliveries(production)
                try:
                    self.assertEqual(reopened.get(job), value)
                finally:
                    reopened.close()

    def test_input_is_bounded_before_reading_any_source(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            p=SimpleNamespace(journal=SimpleNamespace(root=root/'jobs'), driver=SimpleNamespace(
                motions=SimpleNamespace(projects=SimpleNamespace(state_root=root))))
            manager=ProductionDeliveries(p)
            try:
                for value in ([], ['a'], ['a','a'], list(range(17)), 'a'):
                    with self.assertRaisesRegex(RuntimeError, 'sources_invalid'):
                        manager.submit(dict(run_ids=value))
            finally:
                manager.close()
