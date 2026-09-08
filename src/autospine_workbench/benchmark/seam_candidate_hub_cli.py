"""Serve a verified candidate collection without copying the official Runtime."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from .seam_candidate_hub import load_collection


def handler(files):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            name = urlsplit(self.path).path
            raw = files.get(name)
            if raw is None:
                self.send_error(404)
                return
            self.send_response(200)
            mime = 'text/html' if name in ('/', '/player.html') else mimetypes.guess_type(name)[0]
            if name.endswith('.js'):
                mime = 'text/javascript'
            self.send_header('Content-Type', mime or 'application/octet-stream')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    try:
        index, files = load_collection(args.config, args.runtime)
        root = Path(__file__).resolve().parents[3]
        for route, source in {'/': 'web/seam-candidate-hub.html',
                              '/seam-candidate-hub.js': 'web/modules/seam-candidate-hub.js',
                              '/player.html': 'tools/ownership-runtime.html',
                              '/ownership-runtime.js': 'tools/ownership-runtime.js'}.items():
            files[route] = (root / source).read_bytes()
        with ThreadingHTTPServer(('127.0.0.1', args.port), handler(files)) as server:
            receipt = dict(index, url=f'http://127.0.0.1:{server.server_port}/')
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
            print(receipt['url'], flush=True)
            server.serve_forever()
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps(dict(status='blocked', reason_code='candidate_collection_invalid', authority='none')))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
