"""Serve one explicit Spine 4.2 export for an opt-in browser capture."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from autospine_workbench.safe_input_files import (  # noqa: E402
    read_real_file,
    strict_json_object,
)
from autospine_workbench.spine42_runtime_contract import (  # noqa: E402
    build_runtime_session,
)
from autospine_workbench.spine42_runtime_inputs import (  # noqa: E402
    require_export_files,
    require_runtime_package,
)
from autospine_workbench.spine42_runtime_regression import (  # noqa: E402
    Spine42CaptureStore,
)
from autospine_workbench.spine42_runtime_server import (  # noqa: E402
    create_spine42_runtime_server,
)


RUNTIME_ENV = "AUTOSPINE_SPINE42_RUNTIME_ROOT"
LICENSE_ENV = "AUTOSPINE_SPINE42_RUNTIME_LICENSE_ACKNOWLEDGED"
OFFLINE_INSTALL = (
    "npm install --offline --ignore-scripts --no-save --package-lock=false "
    "--prefix workspace/runtime/spine-player-4.2.119 "
    "@esotericsoftware/spine-player@4.2.119"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load one explicit Spine 4.2 export with the official, locally installed "
            "@esotericsoftware/spine-player@4.2.119 and capture its canvas."
        ),
        epilog=(
            "No official runtime is copied into the repository. Offline cached install: "
            + OFFLINE_INSTALL
        ),
    )
    parser.add_argument("--export-dir", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument(
        "--runtime-root", type=Path,
        default=Path(os.environ[RUNTIME_ENV]) if os.environ.get(RUNTIME_ENV) else None,
        help=f"Exact package directory; defaults to ${RUNTIME_ENV}",
    )
    parser.add_argument("--case-id")
    parser.add_argument("--clip", choices=("setup", "idle", "wave.left"), default="setup")
    parser.add_argument("--time", type=float)
    parser.add_argument("--viewport", type=_viewport, default=(640, 640), metavar="WIDTHxHEIGHT")
    parser.add_argument("--dpr", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--background", default="#20242aff")
    parser.add_argument("--golden-contract", type=Path)
    parser.add_argument("--golden-root", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument(
        "--acknowledge-spine-runtime-license", action="store_true",
        help="Confirm the operator is authorized under the official Spine Runtimes license",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    acknowledged = args.acknowledge_spine_runtime_license or os.environ.get(LICENSE_ENV) == "1"
    if not acknowledged:
        parser.error(
            "official Spine runtime use requires --acknowledge-spine-runtime-license "
            f"or {LICENSE_ENV}=1"
        )
    if args.runtime_root is None:
        parser.error(f"--runtime-root or {RUNTIME_ENV} is required; offline setup: {OFFLINE_INSTALL}")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be in [0,65535]")
    clip = None if args.clip == "setup" else args.clip
    default_time = {None: 0.0, "idle": 1.0, "wave.left": 0.6}[clip]
    time_seconds = default_time if args.time is None else args.time
    case_id = args.case_id or {
        None: "setup", "idle": "idle.t1000", "wave.left": "wave-left.t0600"
    }[clip]
    golden = _load_golden(args.golden_contract) if args.golden_contract else None
    golden_root = args.golden_root or (
        args.golden_contract.parent if args.golden_contract else None
    )
    try:
        runtime = require_runtime_package(args.runtime_root)
        exports = require_export_files(args.export_dir)
        session = build_runtime_session(
            exports, viewport=args.viewport, device_pixel_ratio=args.dpr,
            background=args.background,
            case={"id": case_id, "clip": clip, "time_seconds": time_seconds},
        )
        captures = Spine42CaptureStore(
            args.capture_dir, session, golden=golden, golden_root=golden_root
        )
        server = create_spine42_runtime_server(
            args.host, args.port, runtime, exports, session, captures
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    host, port = server.server_address[:2]
    print(f"runtime=@esotericsoftware/spine-player@4.2.119")
    print(f"case={case_id}; clip={clip or 'setup'}; time={time_seconds:.6f}")
    print(f"url=http://{host}:{port}/case/{case_id}")
    print("result_protocol=window.__AUTOSPINE_RUNTIME_RESULT__")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _load_golden(path: Path) -> dict:
    return strict_json_object(read_real_file(path, 1024 * 1024, "runtime golden"),
                              "runtime golden")


def _viewport(value: str) -> tuple[int, int]:
    try:
        width, height = (int(item) for item in value.lower().split("x", 1))
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("viewport must be WIDTHxHEIGHT") from exc
    return width, height


if __name__ == "__main__":
    raise SystemExit(main())
