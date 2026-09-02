"""Version-isolated router for P10.6b MotionInstance v3 commands."""

from __future__ import annotations

from .p10_motion_instance_v3_cli import (
    add_p10_motion_instance_v3_subcommands as add_v1,
    dispatch_p10_motion_instance_v3_command as dispatch_v1,
)
from .p10_motion_instance_v3_v2_cli import (
    add_p10_motion_instance_v3_v2_subcommands as add_v2,
    dispatch_p10_motion_instance_v3_v2_command as dispatch_v2,
)


def add_p10_motion_instance_v3_subcommands(subparsers, state_root) -> None:
    add_v1(subparsers, state_root)
    add_v2(subparsers, state_root)


def dispatch_p10_motion_instance_v3_command(args):
    status = dispatch_v2(args)
    return dispatch_v1(args) if status is None else status


__all__ = [
    "add_p10_motion_instance_v3_subcommands",
    "dispatch_p10_motion_instance_v3_command",
]
