"""Version-preserving P10.7a CLI registration and dispatch."""

from .p10_spine42_v3_cli import (
    add_p10_spine42_v3_subcommands as add_v1,
    dispatch_p10_spine42_v3_command as dispatch_v1,
)
from .p10_spine42_v3_v2_cli import (
    add_p10_spine42_v3_v2_subcommands as add_v2,
    dispatch_p10_spine42_v3_v2_command as dispatch_v2,
)


def add_p10_spine42_v3_subcommands(subparsers, state_root) -> None:
    add_v1(subparsers, state_root)
    add_v2(subparsers, state_root)


def dispatch_p10_spine42_v3_command(args) -> int | None:
    status = dispatch_v1(args)
    return dispatch_v2(args) if status is None else status


__all__ = [
    "add_p10_spine42_v3_subcommands",
    "dispatch_p10_spine42_v3_command",
]
