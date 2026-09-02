"""One-pass orchestration tests for P10.6b v2 commands."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_motion_instance_v3_commands_v2 import (  # noqa: E402
    P10MotionInstanceV3CommandV2Error,
    compile_body_sway_motion_instance_v3_v2_command,
    verify_body_sway_motion_instance_v3_v2_command,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402


TARGET = "autospine_workbench.p10_motion_instance_v3_commands_v2"
SHAS = tuple(f"{index:064x}" for index in range(1, 30))
ADMISSION_SHA = hashlib.sha256(b"admission").hexdigest()
IDENTITY_NAMES = (
    "admission_sha256", "source_set_sha256", "source_document_sha256",
    "dynamic_seam_probe_sha256", "dynamic_seam_bundle_sha256",
    "motion_instance_v2_sha256", "reviewed_motion_bundle_sha256",
    "motion_instance_v3_sha256", "motion_instance_v3_profile_sha256",
    "motion_domain_sha256", "rotation_timeline_sha256",
    "base_channels_sha256", "rig_ir_sha256", "target_profile_sha256",
    "run_sha256", "bundle_sha256",
)


class FakePublished:
    pass


class FakeVerified:
    pass


def local_store(root: Path) -> ProjectStore:
    return ProjectStore(
        root, state_root=root / "state", measure_composite_quality=False,
    )


def capture_reader():
    return type("ReadOnlyJobs", (), {"get": lambda self, _job: {}})()


def dynamic_source():
    return {
        "body_sway_continuous_preview_proof_v2": {"source": {
            "amplitude_envelope_candidate_v2": {"source": {
                "reviewed_probe_report": {"source": {"p9": {
                    "motion_instance_v2_sha256": SHAS[2],
                    "bundle_sha256": SHAS[3],
                }}},
            }},
        }},
    }


def verified_value():
    value = FakeVerified()
    value.project_id = "fixture-project"
    value.clip_id = "idle"
    value.inventory = (
        "body-sway-motion-consumer-admission-v2.json",
        "motion-instance-v3.json", "run-manifest-v2.json",
    )
    value.identities = dict(zip(IDENTITY_NAMES, SHAS[4:20], strict=True))
    for name, item in value.identities.items():
        setattr(value, name, item)
    return value


@contextmanager
def patched_pipeline(*, before=None, after=None, fail_at=None):
    order = []
    dynamic = SimpleNamespace(
        project_id="fixture-project", clip_id="idle", source=dynamic_source(),
        probe_sha256=SHAS[0], bundle_sha256=SHAS[1],
    )
    reviewed = SimpleNamespace(
        project_id="fixture-project", clip_id="idle",
        motion_instance_v2_sha256=SHAS[2], bundle_sha256=SHAS[3],
    )
    observation = lambda marker="same": SimpleNamespace(
        identity_sha256=SHAS[20], canonical_bytes=marker.encode("utf-8"),
    )
    before = before or observation()
    after = after or observation()
    prepared = SimpleNamespace(
        project_id="fixture-project", clip_id="idle",
        admission={"format_version": 2}, admission_bytes=b"admission",
        admission_sha256=ADMISSION_SHA,
    )
    motion = SimpleNamespace(document={"format_version": 3}, sha256=SHAS[11])
    published = FakePublished()
    published.project_id, published.clip_id = "fixture-project", "idle"
    published.admission_sha256 = ADMISSION_SHA
    published.motion_instance_v3_sha256 = SHAS[11]
    published.bundle_sha256 = SHAS[19]
    published.run_sha256 = SHAS[18]
    published.reused = False
    verified = verified_value()
    verified.identities["admission_sha256"] = ADMISSION_SHA
    verified.identities["motion_instance_v3_sha256"] = SHAS[11]
    verified.identities["bundle_sha256"] = SHAS[19]
    verified.identities["run_sha256"] = SHAS[18]
    for name, value in verified.identities.items():
        setattr(verified, name, value)

    def effect(name, value):
        def run(*_args, **_kwargs):
            order.append(name)
            if fail_at == name:
                raise ValueError(r"C:\private\source.json")
            return value
        return run

    dynamic_reader = Mock()
    dynamic_reader.load.side_effect = effect("dynamic", dynamic)
    p9_reader = Mock()
    p9_reader.load.side_effect = effect("p9", reviewed)
    store = Mock()
    store.publish.side_effect = effect("publish", published)
    reader = Mock()
    reader.load.side_effect = effect("readback", verified)
    head_values = iter((before, after))

    def read_head(*_args, **_kwargs):
        order.append("head")
        return next(head_values)

    heads = Mock(side_effect=read_head)
    with ExitStack() as stack:
        stack.enter_context(patch(
            f"{TARGET}.BodySwayDynamicSeamBundleReaderV2",
            return_value=dynamic_reader,
        ))
        stack.enter_context(patch(
            f"{TARGET}.VerifiedReviewedMotionBundleReader",
            return_value=p9_reader,
        ))
        stack.enter_context(patch(
            f"{TARGET}.require_current_body_sway_dynamic_seam_heads_v2",
            heads,
        ))
        stack.enter_context(patch(
            f"{TARGET}.compile_motion_instance_v3_prepared_core_v2",
            side_effect=effect("core", object()),
        ))
        stack.enter_context(patch(
            f"{TARGET}.seal_motion_instance_v3_prepared_v2",
            side_effect=effect("seal", prepared),
        ))
        stack.enter_context(patch(
            f"{TARGET}._require_admission_identity",
            side_effect=effect("admission-identity", None),
        ))
        stack.enter_context(patch(
            f"{TARGET}.compile_motion_instance_v3_v2",
            side_effect=effect("motion", motion),
        ))
        stack.enter_context(patch(
            f"{TARGET}.MotionInstanceV3BundleStoreV2", return_value=store,
        ))
        stack.enter_context(patch(
            f"{TARGET}.MotionInstanceV3BundleReaderV2", return_value=reader,
        ))
        stack.enter_context(patch(
            f"{TARGET}.PublishedMotionInstanceV3BundleV2", FakePublished,
        ))
        stack.enter_context(patch(
            f"{TARGET}.VerifiedMotionInstanceV3BundleV2", FakeVerified,
        ))
        yield SimpleNamespace(
            order=order, dynamic=dynamic, reviewed=reviewed,
            prepared=prepared, published=published, verified=verified,
            dynamic_reader=dynamic_reader, p9_reader=p9_reader,
            heads=heads, store=store, reader=reader,
        )


class P10MotionInstanceV3CommandV2Tests(unittest.TestCase):
    def test_new_production_modules_stay_within_soft_limit(self):
        names = (
            "p10_motion_instance_v3_commands_v2.py",
            "p10_motion_instance_v3_v2_cli.py",
            "p10_motion_instance_v3_stage_cli.py",
        )
        for name in names:
            with self.subTest(name=name):
                lines = (SRC / "autospine_workbench" / name).read_text(
                    encoding="utf-8"
                ).splitlines()
                self.assertLessEqual(len(lines), 300)

    def test_compile_reads_dynamic_once_and_reuses_verified_upstream(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patched_pipeline() as fixture:
            store = local_store(Path(temporary))
            result = compile_body_sway_motion_instance_v3_v2_command(
                capture_reader(), store, "fixture-project",
                dynamic_seam_probe_sha256=SHAS[0],
                dynamic_seam_bundle_sha256=SHAS[1],
            )
        self.assertEqual(
            ["dynamic", "p9", "head", "core", "head", "seal",
             "admission-identity", "motion", "publish", "readback"],
            fixture.order,
        )
        fixture.dynamic_reader.load.assert_called_once_with(
            "fixture-project", SHAS[0], SHAS[1],
        )
        fixture.p9_reader.load.assert_called_once_with(
            "fixture-project", SHAS[2], SHAS[3],
        )
        publish = fixture.store.publish.call_args
        self.assertIs(fixture.prepared, publish.args[0])
        self.assertIs(fixture.dynamic, publish.args[2])
        self.assertIs(fixture.reviewed, publish.args[3])
        readback = fixture.reader.load.call_args
        self.assertIs(fixture.dynamic, readback.kwargs["dynamic_bundle"])
        self.assertIs(fixture.reviewed, readback.kwargs["reviewed_bundle"])
        self.assertIs(fixture.prepared, readback.kwargs["prepared"])
        self.assertEqual("compiled", result.mode)
        self.assertFalse(result.document["head_check"]
                         ["permanent_authority_claimed"])

    def test_head_drift_and_replay_failure_publish_nothing(self):
        cases = (
            {"after": SimpleNamespace(
                identity_sha256=SHAS[21], canonical_bytes=b"same",
            )},
            {"fail_at": "admission-identity"},
        )
        for options in cases:
            with self.subTest(options=tuple(options)), \
                    tempfile.TemporaryDirectory() as temporary, \
                    patched_pipeline(**options) as fixture, \
                    self.assertRaises(P10MotionInstanceV3CommandV2Error):
                compile_body_sway_motion_instance_v3_v2_command(
                    capture_reader(), local_store(Path(temporary)),
                    "fixture-project",
                    dynamic_seam_probe_sha256=SHAS[0],
                    dynamic_seam_bundle_sha256=SHAS[1],
                )
            fixture.store.publish.assert_not_called()
            fixture.reader.load.assert_not_called()

    def test_invalid_address_fails_before_any_bundle_reader(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patched_pipeline() as fixture, \
                self.assertRaises(P10MotionInstanceV3CommandV2Error):
            compile_body_sway_motion_instance_v3_v2_command(
                capture_reader(), local_store(Path(temporary)),
                "fixture-project", dynamic_seam_probe_sha256="bad",
                dynamic_seam_bundle_sha256=SHAS[1],
            )
        fixture.dynamic_reader.load.assert_not_called()

    def test_verify_reads_only_the_explicit_historical_address(self):
        verified = verified_value()
        reader = Mock()
        reader.load.return_value = verified
        with patch(f"{TARGET}.MotionInstanceV3BundleReaderV2",
                   return_value=reader):
            result = verify_body_sway_motion_instance_v3_v2_command(
                Path("state"), "fixture-project",
                motion_instance_v3_sha256=
                    verified.motion_instance_v3_sha256,
                bundle_sha256=verified.bundle_sha256,
            )
        reader.load.assert_called_once_with(
            "fixture-project", verified.motion_instance_v3_sha256,
            verified.bundle_sha256,
        )
        self.assertEqual("verified", result.mode)
        self.assertFalse(result.document["head_check"]
                         ["current_heads_observed"])


if __name__ == "__main__":
    unittest.main()
