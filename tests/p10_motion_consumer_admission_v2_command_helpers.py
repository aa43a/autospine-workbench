"""Isolated orchestration fixtures for the P10.6a v2 command."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch


MODULE = "autospine_workbench.p10_motion_consumer_admission_commands_v2."
SHAS = tuple(character * 64 for character in "abcdef012345")


def dynamic_source():
    return {
        "body_sway_continuous_preview_proof_v2": {
            "source": {
                "amplitude_envelope_candidate_v2": {
                    "source": {
                        "reviewed_probe_report": {
                            "source": {
                                "p9": {
                                    "motion_instance_v2_sha256": SHAS[2],
                                    "bundle_sha256": SHAS[3],
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def admission_document():
    return {
        "format": "autospine-body-sway-motion-consumer-admission",
        "format_version": 2,
        "project_id": "fixture-project",
        "clip_id": "idle",
        "status": "setup_local_timeline_compilation_admitted",
    }


def observation(*, identity=SHAS[6], marker="same"):
    document = {
        "method": "fixture-v2-current-head",
        "scope": "compile_time",
        "identity_sha256": identity,
        "identity": {"marker": marker},
        "permanent_authority_claimed": False,
    }
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return SimpleNamespace(
        identity_sha256=identity, document=document,
        canonical_bytes=encoded,
    )


@contextmanager
def patched_v2_command_pipeline(
    *, before=None, after=None, read_failure=None,
    compile_failure=None, replay_failure=None,
):
    """Patch domain-heavy readers while retaining orchestration order."""

    order = []
    dynamic = SimpleNamespace(
        project_id="fixture-project", clip_id="idle",
        source=dynamic_source(), probe_sha256=SHAS[0],
        bundle_sha256=SHAS[1],
    )
    reviewed = SimpleNamespace(
        project_id="fixture-project", clip_id="idle",
        motion_instance_v2_sha256=SHAS[2], bundle_sha256=SHAS[3],
    )
    core = SimpleNamespace(document={"core": True})
    admission_doc = admission_document()
    admission_bytes = json.dumps(
        admission_doc, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    admission = SimpleNamespace(
        document=admission_doc, canonical_bytes=admission_bytes,
        sha256=hashlib.sha256(admission_bytes).hexdigest(),
    )
    heads = iter((before or observation(), after or observation()))

    def step(name, value=None, failure=None):
        def run(*_args, **_kwargs):
            order.append(name)
            if failure is not None:
                raise failure
            return value
        return run

    def head(*_args, **_kwargs):
        order.append("head")
        return next(heads)

    with ExitStack() as stack:
        dynamic_reader = stack.enter_context(patch(
            MODULE + "BodySwayDynamicSeamBundleReaderV2"
        ))
        dynamic_reader.return_value.load.side_effect = step(
            "dynamic", dynamic, read_failure,
        )
        reviewed_reader = stack.enter_context(patch(
            MODULE + "VerifiedReviewedMotionBundleReader"
        ))
        reviewed_reader.return_value.load.side_effect = step(
            "p9", reviewed,
        )
        head_check = stack.enter_context(patch(
            MODULE + "require_current_body_sway_dynamic_seam_heads_v2",
            side_effect=head,
        ))
        compiler = stack.enter_context(patch(
            MODULE + "compile_body_sway_motion_consumer_admission_core_v2",
            side_effect=step("core", core, compile_failure),
        ))
        sealer = stack.enter_context(patch(
            MODULE + "seal_body_sway_motion_consumer_admission_v2",
            side_effect=step("seal", admission),
        ))
        replay = stack.enter_context(patch(
            MODULE +
            "body_sway_motion_consumer_admission_canonical_bytes_v2",
            side_effect=step("replay", admission_bytes, replay_failure),
        ))
        yield SimpleNamespace(
            order=order, dynamic=dynamic, reviewed=reviewed, core=core,
            admission=admission, dynamic_reader=dynamic_reader,
            reviewed_reader=reviewed_reader, head_check=head_check,
            compiler=compiler, sealer=sealer, replay=replay,
        )
