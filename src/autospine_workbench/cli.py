"""Command-line entry point for the AutoSpine workbench."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .server import create_server


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m autospine_workbench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Run the local workbench HTTP API")
    serve.add_argument("--host", default="127.0.0.1", help="Loopback host (default: 127.0.0.1)")
    serve.add_argument("--port", default=8765, type=int, help="TCP port (default: 8765)")
    serve.add_argument(
        "--workspace",
        type=Path,
        default=_project_root().parent,
        help="Workspace containing tmp/psd_audit/results",
    )
    serve.add_argument(
        "--state-root",
        type=Path,
        default=_project_root() / "workspace",
        help="Directory for atomic override state",
    )
    serve.add_argument(
        "--web-root",
        type=Path,
        default=None,
        help="Optional built frontend directory to serve",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "serve":
        raise AssertionError(f"Unhandled command: {args.command}")
    try:
        server = create_server(
            args.host,
            args.port,
            args.workspace,
            web_root=args.web_root,
            state_root=args.state_root,
        )
    except (OSError, ValueError) as exc:
        build_parser().error(str(exc))
    bound_host, bound_port = server.server_address[:2]
    print(f"AutoSpine workbench serving on http://{bound_host}:{bound_port}")
    print(f"Workspace: {Path(args.workspace).expanduser().resolve()}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping AutoSpine workbench.")
    finally:
        server.server_close()
    return 0

