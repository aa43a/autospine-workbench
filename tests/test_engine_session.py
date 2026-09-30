"""Engine lifecycle tests use fresh temporary state and no production jobs."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

from autospine_workbench.engine_session import EngineSessionLease, SCHEMA
from autospine_workbench.server import create_server
from test_project_store import StoreFixture


class EngineSessionTests(TestCase):
    def test_os_lease_blocks_another_process_and_is_released_by_close(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            lease = EngineSessionLease(root/'state', root)
            command = [sys.executable, '-c',
                'from autospine_workbench.engine_session import EngineSessionLease;'
                'import sys; EngineSessionLease(sys.argv[1],sys.argv[2])',
                str(root/'state'), str(root)]
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
            try:
                second = subprocess.run(command, capture_output=True, env=env, timeout=10)
                self.assertNotEqual(second.returncode, 0)
                self.assertIn(b'owned or ownership', second.stderr)
                self.assertFalse(os.get_inheritable(lease._descriptor))
            finally:
                lease.close()
            second = subprocess.run(command, capture_output=True, env=env, timeout=10)
            self.assertEqual(second.returncode, 0, second.stderr)

    def test_crash_releases_ownership_and_stale_registration_has_no_authority(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            command = [sys.executable, '-c',
                'from autospine_workbench.engine_session import EngineSessionLease;'
                'import os,sys; lease=EngineSessionLease(sys.argv[1],sys.argv[2]);'
                'lease.publish("http://127.0.0.1:12345"); os._exit(0)',
                str(root/'state'), str(root)]
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
            result = subprocess.run(command, capture_output=True, env=env, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = root/'state/engine-session-v1/endpoint.json'
            stale = json.loads(record.read_text())
            lease = EngineSessionLease(root/'state', root)
            try:
                current = lease.publish('http://127.0.0.1:12346')
                self.assertNotEqual(current['nonce'], stale['nonce'])
                self.assertEqual(current['pid'], os.getpid())
                self.assertEqual(json.loads(record.read_text()), current)
            finally:
                lease.close()
            self.assertFalse(record.exists())

    def test_actual_bound_endpoint_matches_health_and_second_service_cannot_recover_jobs(self):
        with TemporaryDirectory() as folder:
            fixture = StoreFixture(Path(folder))
            server = create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                record = json.loads((fixture.state/'engine-session-v1/endpoint.json').read_text())
                self.assertEqual(record['schema'], SCHEMA)
                self.assertEqual(record['origin'], f'http://127.0.0.1:{server.server_port}')
                self.assertEqual(record['state_root'], str(fixture.state.resolve()))
                self.assertEqual(record['workspace_root'], str(fixture.workspace.resolve()))
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                connection.request('GET', '/api/health')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(json.loads(response.read())['engine_session'], record)
                connection.close()
                with patch('autospine_workbench.server.start_workbench_managers') as factory:
                    with self.assertRaisesRegex(OSError, 'owned or ownership'):
                        create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
                    factory.assert_not_called()
                self.assertEqual(json.loads((fixture.state/'engine-session-v1/endpoint.json').read_text()), record)
            finally:
                server.shutdown(); server.server_close(); thread.join(5)
            self.assertFalse((fixture.state/'engine-session-v1/endpoint.json').exists())
            restarted = create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
            restarted.server_close()

    def test_failed_startup_bind_or_registration_releases_state(self):
        with TemporaryDirectory() as folder:
            fixture = StoreFixture(Path(folder))
            with patch('autospine_workbench.server.start_workbench_managers', side_effect=OSError('startup failed')):
                with self.assertRaisesRegex(OSError, 'startup failed'):
                    create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
            lease = EngineSessionLease(fixture.state, fixture.workspace); lease.close()
            blocker = socket.socket(); blocker.bind(('127.0.0.1', 0)); blocker.listen()
            try:
                with self.assertRaisesRegex(OSError, 'Could not bind'):
                    create_server('127.0.0.1', blocker.getsockname()[1], fixture.workspace, state_root=fixture.state)
            finally:
                blocker.close()
            lease = EngineSessionLease(fixture.state, fixture.workspace); lease.close()
            with patch.object(EngineSessionLease, 'publish', side_effect=OSError('registration failed')):
                with self.assertRaisesRegex(OSError, 'registration failed'):
                    create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
            restarted = create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
            restarted.server_close()

    def test_stale_desktop_nonce_is_rejected_before_any_dispatch_and_browser_without_header_still_works(self):
        with TemporaryDirectory() as folder:
            fixture = StoreFixture(Path(folder))
            server = create_server('127.0.0.1', 0, fixture.workspace, state_root=fixture.state)
            thread = Thread(target=server.serve_forever); thread.start()
            try:
                nonce = server.engine_session['nonce']
                for method in ('GET', 'HEAD', 'PUT', 'POST', 'OPTIONS'):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    with patch('autospine_workbench.server.dispatch_workbench_api_post') as post, \
                            patch('autospine_workbench.server.dispatch_workbench_api_put') as put, \
                            patch('autospine_workbench.server.dispatch_workbench_api_get') as get:
                        connection.request(method, '/api/production', body='{}', headers={'X-Autospine-Engine-Session':'b'*32})
                        response = connection.getresponse()
                        self.assertEqual(response.status, 409)
                        self.assertEqual(response.getheader('X-Autospine-Engine-Session-Mismatch'), '1')
                        raw = response.read()
                        if method != 'HEAD':
                            self.assertEqual(json.loads(raw)['error'], 'engine_session_changed')
                        post.assert_not_called(); put.assert_not_called(); get.assert_not_called()
                    connection.close()
                for supplied in (None, nonce):
                    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                    connection.request('GET','/api/health',headers={} if supplied is None else {'X-Autospine-Engine-Session':supplied})
                    response = connection.getresponse(); self.assertEqual(response.status,200)
                    self.assertEqual(json.loads(response.read())['engine_session']['nonce'],nonce)
                    connection.close()
                connection = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                connection.putrequest('GET','/api/health')
                connection.putheader('X-Autospine-Engine-Session',nonce)
                connection.putheader('X-Autospine-Engine-Session',nonce)
                connection.endheaders()
                response=connection.getresponse();self.assertEqual(response.status,409);response.read();connection.close()
            finally:
                server.shutdown(); server.server_close(); thread.join(5)
