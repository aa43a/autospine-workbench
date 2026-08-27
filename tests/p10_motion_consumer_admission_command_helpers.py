"""Isolated fixtures for P10.6a command orchestration tests."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE = "autospine_workbench.p10_motion_consumer_admission_commands."
SHAS = tuple(character * 64 for character in "abcdef")


def probe_document() -> dict:
    return {
        "format": "fixture-dynamic-seam-probe",
        "format_version": 1,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "source": {
            "body_sway_continuous_preview_proof": {
                "source": {
                    "amplitude_envelope_candidate": {
                        "source": {
                            "reviewed_probe_report": {
                                "source": {
                                    "p9": {
                                        "motion_instance_v2_sha256": SHAS[1],
                                        "bundle_sha256": SHAS[2],
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }


def admission_document() -> dict:
    return {
        "format": "autospine-body-sway-motion-consumer-admission",
        "format_version": 1,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "status": "fixture-admitted",
    }


def observation(*, identity="same-head", marker="same-document"):
    document = {
        "method": "fixture-current-head-check",
        "scope": "compile_time",
        "identity": {"marker": marker},
        "permanent_authority_claimed": False,
    }
    return SimpleNamespace(
        identity=identity,
        document=deepcopy(document),
        canonical_bytes=json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
    )


def write_probe(root: Path, *, raw: str | None = None) -> Path:
    path = root / "private" / "dynamic-seam-probe.json"
    path.parent.mkdir()
    path.write_text(
        raw if raw is not None else json.dumps(probe_document()),
        encoding="utf-8",
    )
    return path


@contextmanager
def patched_command_pipeline(
    *, before=None, after=None, events=None,
    probe_failure=None, compile_failure=None, validation_failure=None,
):
    """Patch domain-heavy replay while preserving command ordering."""

    order = [] if events is None else events
    first, second = before or observation(), after or observation()
    bundle = SimpleNamespace(
        project_id="fixture-project",
        clip_id="idle",
        motion_instance_v2_sha256=SHAS[1],
        bundle_sha256=SHAS[2],
    )
    core = SimpleNamespace(document={"core": True})
    admission = SimpleNamespace(
        document=admission_document(), sha256=SHAS[4]
    )

    def step(name, value=None, failure=None):
        def run(*_args, **_kwargs):
            order.append(name)
            if failure is not None:
                raise failure
            return value
        return run

    heads = iter((first, second))

    def check_heads(*_args, **_kwargs):
        order.append("head")
        return next(heads)

    with ExitStack() as stack:
        probe_hash = stack.enter_context(patch(
            MODULE + "body_sway_dynamic_seam_probe_sha256",
            side_effect=step("probe-hash", SHAS[0], probe_failure),
        ))
        reader_class = stack.enter_context(patch(
            MODULE + "VerifiedReviewedMotionBundleReader"
        ))
        reader_class.return_value.load.side_effect = step("bundle", bundle)
        head_check = stack.enter_context(patch(
            MODULE + "require_current_body_sway_dynamic_seam_heads",
            side_effect=check_heads,
        ))
        compiler = stack.enter_context(patch(
            MODULE + "compile_body_sway_motion_consumer_admission_core",
            side_effect=step("compile", core, compile_failure),
        ))
        sealer = stack.enter_context(patch(
            MODULE + "seal_body_sway_motion_consumer_admission",
            side_effect=step("seal", admission),
        ))
        validator = stack.enter_context(patch(
            MODULE + "require_body_sway_motion_consumer_admission",
            side_effect=step("validate", None, validation_failure),
        ))
        admission_hash = stack.enter_context(patch(
            MODULE + "body_sway_motion_consumer_admission_sha256",
            side_effect=step("admission-hash", SHAS[4]),
        ))
        yield SimpleNamespace(
            order=order, bundle=bundle, core=core, admission=admission,
            probe_hash=probe_hash, reader_class=reader_class,
            head_check=head_check, compiler=compiler, sealer=sealer,
            validator=validator, admission_hash=admission_hash,
        )
