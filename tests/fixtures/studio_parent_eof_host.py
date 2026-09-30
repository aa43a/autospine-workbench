"""Run the actual Studio launcher against a blocking disposable server."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import types


launcher_file, fixture_name, engine_name = sys.argv[1:]
source = Path(launcher_file).read_text(encoding='utf-8')
launcher = source.split('const launcher = String.raw`', 1)[1].split('\n`;', 1)[0]
fixture = Path(fixture_name)
sys.argv = ['-c', engine_name, str(fixture/'workspace'), str(fixture/'state'), '', '', 'fixture-token']
module = types.ModuleType('autospine_workbench.server')


class FakeServer:
    def __init__(self):
        self.server_port = 34567
        self.engine_session = dict(schema='autospine.engine-session/v1', nonce='a'*32,
            pid=os.getpid(), state_root=sys.argv[3], workspace_root=sys.argv[2], origin='http://127.0.0.1:34567')
        self.stop = threading.Event()

    def serve_forever(self, **kwargs):
        self.stop.wait()

    def shutdown(self):
        self.stop.set()

    def server_close(self):
        (fixture/'closing').write_text('entered')
        time.sleep(60)


module.create_server = lambda *args: FakeServer()
sys.modules['autospine_workbench.server'] = module
exec(compile(launcher, str(launcher_file), 'exec'), {})
