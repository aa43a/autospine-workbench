"""Small isolated fixtures for P10.5d command orchestration tests."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


MODULE = "autospine_workbench.p10_dynamic_seam_commands."
SHAS = tuple(character * 64 for character in "abcdef")


def proof_document() -> dict:
    return {
        "format": "fixture-continuous-proof",
        "format_version": 1,
        "project_id": "fixture-project",
        "clip_id": "idle",
    }


def source_document() -> dict:
    return {
        "source_set_sha256": SHAS[3],
        "body_sway_continuous_proof_sha256": SHAS[0],
        "reviewed_seam_anchor_set_sha256": SHAS[1],
        "reviewed_seam_anchor_set_bundle_sha256": SHAS[2],
        "body_sway_continuous_preview_proof": proof_document(),
    }


def probe_document() -> dict:
    return {
        "format": "autospine-body-sway-dynamic-seam-probe",
        "format_version": 1,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "status": "fixture-status",
    }


def observation(*, identity="same-head", marker="same-document"):
    document = {
        "method": "visual-review-double-snapshot-plus-seam-review-history-a-b",
        "scope": "compile_time",
        "identity": {"marker": marker},
        "checks": {"heads": "current"},
        "permanent_authority_claimed": False,
    }
    return SimpleNamespace(
        identity=identity,
        document=deepcopy(document),
        canonical_bytes=json.dumps(
            document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"),
    )


def write_proof(root: Path, *, raw: str | None = None) -> Path:
    path = root / "private" / "continuous-proof.json"
    path.parent.mkdir()
    path.write_text(
        raw if raw is not None else json.dumps(proof_document()),
        encoding="utf-8",
    )
    return path


@contextmanager
def patched_command_pipeline(
    *,
    before=None,
    after=None,
    events: list[str] | None = None,
    proof_failure=None,
    source_failure=None,
    validator_failure=None,
):
    """Patch domain-heavy replay while preserving command ordering."""

    order = [] if events is None else events
    first = before or observation()
    second = after or observation()
    bundle = SimpleNamespace(
        project_id="fixture-project",
        set_sha256=SHAS[1],
        bundle_sha256=SHAS[2],
        candidates={"candidate": True},
        decision={"decision": True},
        reviewed_set={"reviewed_set": True},
    )
    probe = SimpleNamespace(
        document=probe_document(),
        sha256=SHAS[4],
    )

    def step(name, value=None, failure=None):
        def run(*_args, **_kwargs):
            order.append(name)
            if failure is not None:
                raise failure
            return deepcopy(value)
        return run

    heads = iter((first, second))

    def check_heads(*_args, **_kwargs):
        order.append("head")
        return next(heads)

    with ExitStack() as stack:
        proof_hash = stack.enter_context(patch(
            MODULE + "body_sway_continuous_proof_sha256",
            side_effect=step("proof", SHAS[0], proof_failure),
        ))
        reader_class = stack.enter_context(patch(
            MODULE + "VerifiedReviewedSeamAnchorSetBundleReader"
        ))
        reader_class.return_value.load.side_effect = step(
            "bundle", bundle
        )
        source_builder = stack.enter_context(patch(
            MODULE + "build_body_sway_dynamic_seam_source",
            side_effect=step("source", source_document(), source_failure),
        ))
        head_check = stack.enter_context(patch(
            MODULE + "require_current_body_sway_dynamic_seam_heads",
            side_effect=check_heads,
        ))
        compiler = stack.enter_context(patch(
            MODULE + "compile_body_sway_dynamic_seam_probe",
            side_effect=step("compile", probe),
        ))
        validator = stack.enter_context(patch(
            MODULE + "require_body_sway_dynamic_seam_probe",
            side_effect=step("validate", None, validator_failure),
        ))
        probe_hash = stack.enter_context(patch(
            MODULE + "body_sway_dynamic_seam_probe_sha256",
            side_effect=step("probe-hash", SHAS[4]),
        ))
        yield SimpleNamespace(
            order=order,
            bundle=bundle,
            probe=probe,
            proof_hash=proof_hash,
            reader_class=reader_class,
            source_builder=source_builder,
            head_check=head_check,
            compiler=compiler,
            validator=validator,
            probe_hash=probe_hash,
        )
