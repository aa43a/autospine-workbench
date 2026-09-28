"""Development route harness: real M5 queue, read-only workbench project proxy.

No legacy Runtime controller is started, and no existing task is interrupted.
This is for integration tests while the main workbench finishes other jobs.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen
from urllib.parse import urlsplit, unquote

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.http_security import host_header_is_local
from autospine_workbench.http_workbench_response import WorkbenchResponseMixin
from autospine_workbench.http_static_response import serve_static_response
from autospine_workbench.automation.character_jobs import CharacterJobs
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
from autospine_workbench.automation.motion_intake_routes import dispatch_motions


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--port', type=int, default=8919)
    options = args.parse_args()
    repo = Path(__file__).resolve().parents[1]
    projects = ProjectStore(repo.parent, repo/'workspace')
    sleeves = SleeveWebJobs(projects); characters = CharacterJobs(projects, sleeves)
    motions = MotionIntakeJobs(projects); motions.character_manager = lambda: characters

    class Handler(WorkbenchResponseMixin, BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def dispatch(self, method):
            if not host_header_is_local(self.headers.get('Host')):
                self._send_json(403, {'reason_code':'forbidden_host'}); return
            path = unquote(urlsplit(self.path).path)
            parts = path.strip('/').split('/') if path.strip('/') else []
            if any(p in ('.', '..', '') for p in parts) or '\\' in path:
                self._send_json(400, {'reason_code':'invalid_path'}); return
            if method == 'POST':
                if not (parts[:2] == ['api', 'motions'] and (
                        len(parts) == 4 and (parts[3] == 'joint-animation' or
                         parts[3] in ('cancel', 'retry') and parts[2] in motions._jobs) or
                        len(parts) == 6 and parts[3] == 'related-candidates' and parts[5] == 'joint-animation')):
                    self._send_json(405, {'reason_code':'joint_harness_mutation_scope'}); return
            if dispatch_motions(parts, self, method):
                return
            if method in ('GET', 'HEAD') and parts[:2] == ['api', 'projects']:
                try:
                    with urlopen('http://127.0.0.1:8918'+self.path, timeout=90) as response:
                        self._send_bytes(response.status, response.read(128 << 20), response.headers['Content-Type'])
                except HTTPError as error:
                    self._send_bytes(error.code, error.read(), 'application/json')
                return
            if method in ('GET', 'HEAD') and serve_static_response(parts, repo/'web', self._send_static_file):
                return
            self._send_json(404, {'reason_code':'joint_harness_route_not_found'})

        def do_GET(self): self.dispatch('GET')
        def do_HEAD(self): self.dispatch('HEAD')
        def do_POST(self): self.dispatch('POST')
        def do_OPTIONS(self): self.dispatch('OPTIONS')

    server = ThreadingHTTPServer(('127.0.0.1', options.port), Handler)
    server.automation_manager = SimpleNamespace(_lock=RLock(), _closed=False, _motions=motions)
    print(f'M5 integration server: http://127.0.0.1:{options.port}/motion-editor.html', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close(); motions.close(); characters.close(); sleeves.close()


if __name__ == '__main__': main()
