"""Orchestration, head fencing, verification, and CLI tests for P10.5d v2."""

from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_dynamic_seam_commands_v2 import (  # noqa: E402
    P10DynamicSeamCommandResultV2,
    P10DynamicSeamCommandV2Error,
    compile_body_sway_dynamic_seam_probe_v2_command,
    verify_body_sway_dynamic_seam_bundle_v2_command,
)
from autospine_workbench.p10_dynamic_seam_v2_cli import (  # noqa: E402
    COMPILE_COMMAND,
    ERROR_CODE,
    VERIFY_COMMAND,
)
from autospine_workbench.projection_stage_cli import (  # noqa: E402
    add_projection_stage_subcommands,
    dispatch_projection_stage_command,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402


COMMANDS = "autospine_workbench.p10_dynamic_seam_commands_v2."
CLI_COMPILE = (
    "autospine_workbench.p10_dynamic_seam_v2_cli."
    "compile_body_sway_dynamic_seam_probe_v2_command"
)
CLI_VERIFY = (
    "autospine_workbench.p10_dynamic_seam_v2_cli."
    "verify_body_sway_dynamic_seam_bundle_v2_command"
)
SHAS = tuple(character * 64 for character in "abcdef")


def _fixture():
    source = {
        "project_id": "fixture-project", "clip_id": "idle",
        "source_set_sha256": SHAS[0],
        "body_sway_continuous_preview_proof_v2_sha256": SHAS[1],
        "reviewed_seam_anchor_set_v1_sha256": SHAS[2],
        "reviewed_seam_anchor_set_v1_bundle_sha256": SHAS[3],
    }
    bundle = SimpleNamespace(
        candidates={"kind": "candidate"},
        decision={"kind": "decision"},
        reviewed_set={"kind": "set"},
        bundle_sha256=SHAS[3],
    )
    inputs = SimpleNamespace(
        project_id="fixture-project", safety_run_id=SHAS[4],
        continuous_proof_sha256=SHAS[1],
        reviewed_set_sha256=SHAS[2],
        reviewed_set_bundle_sha256=SHAS[3],
        continuous_proof={"kind": "continuous-v2"},
        reviewed_bundle=bundle,
    )
    probe_document = {
        "project_id": "fixture-project", "clip_id": "idle",
        "source": deepcopy(source), "status": "indeterminate",
        "summary": {"segment_count": 3},
        "claims": {"release_authority": False},
        "release_gate": {"status": "blocked"},
    }
    probe = SimpleNamespace(document=probe_document, sha256=SHAS[5])
    published = SimpleNamespace(
        project_id="fixture-project", clip_id="idle",
        source_set_sha256=SHAS[0], source_document_sha256=SHAS[4],
        probe_sha256=SHAS[5], bundle_sha256=SHAS[0], reused=False,
    )
    verified = SimpleNamespace(
        source=deepcopy(source), probe=deepcopy(probe_document),
        project_id="fixture-project", clip_id="idle",
        source_set_sha256=SHAS[0], source_document_sha256=SHAS[4],
        probe_sha256=SHAS[5], bundle_sha256=SHAS[0],
        manifest={"authority_scope": "historical_exact_bytes_only"},
    )
    observation = SimpleNamespace(
        identity_sha256=SHAS[0], canonical_bytes=b"same-head",
        document={"identity_sha256": SHAS[0]},
    )
    return source, inputs, probe, published, verified, observation


@contextmanager
def _pipeline(*, observations=None):
    source, inputs, probe, published, verified, observation = _fixture()
    order = []
    heads = observations or [observation, observation, observation]
    head_rows = iter(heads)

    def observe_head(*_args, **_kwargs):
        order.append("head")
        return next(head_rows)

    with ExitStack() as stack:
        load = stack.enter_context(patch(
            COMMANDS + "load_p10_dynamic_seam_inputs_v2",
            side_effect=lambda *_args, **_kwargs: (
                order.append("inputs") or inputs
            ),
        ))
        build = stack.enter_context(patch(
            COMMANDS + "build_body_sway_dynamic_seam_source_v2",
            side_effect=lambda **_kwargs: order.append("source") or source,
        ))
        head = stack.enter_context(patch(
            COMMANDS + "_observe_admitted_body_sway_dynamic_seam_heads_v2",
            side_effect=observe_head,
        ))
        compiler = stack.enter_context(patch(
            COMMANDS + "compile_body_sway_dynamic_seam_probe_v2",
            side_effect=lambda *_args, **_kwargs: (
                order.append("compile") or probe
            ),
        ))
        validator = stack.enter_context(patch(
            COMMANDS + "require_body_sway_dynamic_seam_probe_v2",
            side_effect=lambda *_args, **_kwargs: order.append("validate"),
        ))
        store_class = stack.enter_context(patch(
            COMMANDS + "BodySwayDynamicSeamBundleStoreV2"
        ))
        store_class.return_value.publish.side_effect = (
            lambda *_args: order.append("publish") or published
        )
        reader_class = stack.enter_context(patch(
            COMMANDS + "BodySwayDynamicSeamBundleReaderV2"
        ))
        reader_class.return_value.load.side_effect = (
            lambda *_args: order.append("readback") or verified
        )
        yield SimpleNamespace(
            source=source, inputs=inputs, probe=probe,
            published=published, verified=verified,
            observation=observation, order=order, load=load,
            build=build, head=head, compiler=compiler,
            validator=validator, store_class=store_class,
            reader_class=reader_class,
        )


def _store(root):
    return ProjectStore(root, state_root=root / "state",
                        measure_composite_quality=False)


def _compile(store):
    return compile_body_sway_dynamic_seam_probe_v2_command(
        SimpleNamespace(get=lambda _job: {}), store,
        "fixture-project", SHAS[4],
        continuous_proof_sha256=SHAS[1],
        reviewed_set_sha256=SHAS[2],
        reviewed_set_bundle_sha256=SHAS[3],
    )


class P10DynamicSeamCommandV2Tests(unittest.TestCase):
    def test_exact_inputs_three_head_checks_publish_and_readback_order(self):
        with tempfile.TemporaryDirectory() as temporary, _pipeline() as fixture:
            result = _compile(_store(Path(temporary)))
        self.assertEqual([
            "inputs", "source", "head", "compile", "validate", "head",
            "publish", "head", "readback",
        ], fixture.order)
        document = result.document
        self.assertEqual("compiled", document["status"])
        self.assertEqual(SHAS[5], document["probe_sha256"])
        for name in ("before", "prepublish", "postpublish"):
            self.assertEqual(
                fixture.observation.document,
                document["head_observation"][name],
            )
        self.assertFalse(document["head_observation"][
            "permanent_authority_claimed"
        ])
        fixture.load.assert_called_once()
        fixture.build.assert_called_once_with(
            continuous_proof_v2=fixture.inputs.continuous_proof,
            seam_anchor_candidates_v1=
                fixture.inputs.reviewed_bundle.candidates,
            seam_anchor_review_decision_v1=
                fixture.inputs.reviewed_bundle.decision,
            reviewed_seam_anchor_set_v1=
                fixture.inputs.reviewed_bundle.reviewed_set,
            reviewed_set_v1_bundle_sha256=SHAS[3],
        )

    def test_head_change_before_or_after_publication_fails_without_downgrade(self):
        _source_value, _inputs, _probe, _published, _verified, stable = (
            _fixture()
        )
        changed = SimpleNamespace(
            identity_sha256=SHAS[5], canonical_bytes=b"changed",
            document={"identity_sha256": SHAS[5]},
        )
        cases = (
            ([stable, changed], False),
            ([stable, stable, changed], True),
        )
        for heads, published in cases:
            with self.subTest(published=published), \
                    tempfile.TemporaryDirectory() as temporary, \
                    _pipeline(observations=heads) as fixture, \
                    self.assertRaises(P10DynamicSeamCommandV2Error):
                _compile(_store(Path(temporary)))
            self.assertEqual(
                published, fixture.store_class.return_value.publish.called
            )
            fixture.reader_class.return_value.load.assert_not_called()

    def test_historical_verify_never_checks_current_heads(self):
        _source_value, _inputs, _probe, _published, verified, _head = (
            _fixture()
        )
        with patch(
            COMMANDS + "BodySwayDynamicSeamBundleReaderV2"
        ) as reader, patch(
            COMMANDS + "_observe_admitted_body_sway_dynamic_seam_heads_v2"
        ) as current:
            reader.return_value.load.return_value = verified
            result = verify_body_sway_dynamic_seam_bundle_v2_command(
                Path("state"), "fixture-project",
                probe_sha256=SHAS[5], bundle_sha256=SHAS[0],
            )
        document = result.document
        self.assertEqual("verified", document["status"])
        self.assertFalse(document["current_head_checked"])
        self.assertFalse(document["permanent_current_authority_claimed"])
        self.assertEqual("historical_exact_bytes_only",
                         document["authority_scope"])
        current.assert_not_called()

    def test_result_is_copy_isolated(self):
        result = P10DynamicSeamCommandResultV2(
            "fixture-project", "idle", SHAS[0], SHAS[1],
            json.dumps({"status": "verified"}),
        )
        first = result.document
        first["status"] = "forged"
        self.assertEqual("verified", result.document["status"])


def _parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_projection_stage_subcommands(subparsers, Path("default-state"))
    return parser


def _compile_argv():
    return [
        COMPILE_COMMAND, "fixture-project", SHAS[4],
        "--continuous-proof-sha256", SHAS[1],
        "--reviewed-set-sha256", SHAS[2],
        "--reviewed-set-bundle-sha256", SHAS[3],
        "--workspace", "private-workspace", "--state-root", "private-state",
    ]


class P10DynamicSeamCliV2Tests(unittest.TestCase):
    @patch(CLI_COMPILE)
    def test_compile_cli_requires_exact_addresses_and_is_path_free(self, command):
        command.return_value = P10DynamicSeamCommandResultV2(
            "fixture-project", "idle", SHAS[5], SHAS[0],
            json.dumps({"status": "compiled", "probe_sha256": SHAS[5]}),
        )
        parser = _parser()
        parsed = parser.parse_args(_compile_argv())
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(parsed)
        payload = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertTrue(payload["ok"])
        self.assertNotIn("private-", output.getvalue())
        command.assert_called_once()
        for option in (
            "--continuous-proof-sha256", "--reviewed-set-sha256",
            "--reviewed-set-bundle-sha256",
        ):
            values = _compile_argv()
            index = values.index(option)
            del values[index:index + 2]
            with self.subTest(option=option), redirect_stderr(
                io.StringIO()
            ), self.assertRaises(SystemExit):
                parser.parse_args(values)

    @patch(CLI_VERIFY)
    def test_verify_cli_and_redacted_failure(self, command):
        command.return_value = P10DynamicSeamCommandResultV2(
            "fixture-project", "idle", SHAS[5], SHAS[0],
            json.dumps({"status": "verified", "current_head_checked": False}),
        )
        parser = _parser()
        argv = [
            VERIFY_COMMAND, "fixture-project",
            "--probe-sha256", SHAS[5], "--bundle-sha256", SHAS[0],
        ]
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(parser.parse_args(argv))
        self.assertEqual(0, status)
        self.assertFalse(json.loads(output.getvalue())["current_head_checked"])
        command.side_effect = P10DynamicSeamCommandV2Error(
            r"C:\private\artifact.json"
        )
        with redirect_stdout(io.StringIO()) as output:
            status = dispatch_projection_stage_command(parser.parse_args(argv))
        payload = json.loads(output.getvalue())
        self.assertEqual(2, status)
        self.assertEqual(ERROR_CODE, payload["error_code"])
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
