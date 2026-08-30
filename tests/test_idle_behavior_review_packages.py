"""Exact, path-free discovery tests for P10 idle-behavior review packages."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.depth_order_inputs import (  # noqa: E402
    require_depth_order_inputs,
)
from autospine_workbench.depth_order_candidate_validation import (  # noqa: E402
    depth_order_candidates_sha256,
)
from autospine_workbench.foot_lock_candidate_validation import (  # noqa: E402
    foot_lock_candidates_sha256,
)
from autospine_workbench.idle_behavior_review_address import (  # noqa: E402
    IdleBehaviorReviewAddress,
    IdleBehaviorReviewAddressError,
)
from autospine_workbench.idle_behavior_review_packages import (  # noqa: E402
    IdleBehaviorReviewPackageError,
    _adopted_runs,
    get_idle_behavior_review_address,
    list_idle_behavior_review_packages,
)
from autospine_workbench.idle_behavior_review_replay_cache import (  # noqa: E402
    IdleBehaviorReviewReplayCacheError,
)
from autospine_workbench.motion_instance_v2_compiler import (  # noqa: E402
    compile_motion_instance_v2,
)
from autospine_workbench.motion_policy_decision import (  # noqa: E402
    build_motion_policy_decision,
)
from autospine_workbench.reviewed_motion_bundle_store import (  # noqa: E402
    ReviewedMotionBundleStore,
)
from autospine_workbench.reviewed_motion_bundle_reader import (  # noqa: E402
    VerifiedReviewedMotionBundleReaderError,
)
from autospine_workbench.reviewed_motion_bundle_upstream import (  # noqa: E402
    require_reviewed_motion_upstreams,
)
from autospine_workbench.reviewed_motion_policy import (  # noqa: E402
    compile_reviewed_motion_policy,
)
from tests.motion_policy_decision_helpers import (  # noqa: E402
    MotionPolicyDecisionFixture,
    approved_review,
)
from tests.motion_policy_review_package_helpers import (  # noqa: E402
    write_review_package,
)
from tests.p10_candidate_helpers import P10PersistedFixture  # noqa: E402


class _ExactP9Fixture:
    """One real review package plus optional immutable P9 adoptions."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state = self.root / "state"
        self.source = MotionPolicyDecisionFixture(self.root / "upstream")
        upstream = self.source.upstream
        self.verified = {}
        inputs = require_depth_order_inputs(
            upstream.projected, upstream.retarget, upstream.mesh,
        )
        self.depth_pair_policy = upstream.policy(inputs)
        write_review_package(
            self.state,
            self.depth_pair_policy,
            self.source.foot,
            self.source.depth,
            motion_id="motion-a",
        )
        package_list = list_idle_behavior_review_packages(self.state)
        if package_list["count"] != 0:
            raise AssertionError("Fixture must start without a P9 adoption")
        base, target = require_reviewed_motion_upstreams(
            upstream.mesh, upstream.retarget,
        )
        self.base = base
        self.target = target

    def publish(self, revision: int = 1):
        artifact = build_motion_policy_decision(
            self.source.foot,
            self.source.depth,
            review=approved_review(revision),
            decisions=self.source.accept_all(),
            root_release_keys=[],
            draw_order_loop_reset={"mode": "explicit", "approved": False},
        )
        policy = compile_reviewed_motion_policy(
            artifact.document,
            self.source.foot,
            self.source.depth,
            self.source.upstream.mesh,
        ).document
        instance = compile_motion_instance_v2(
            self.base, self.target, policy,
        ).document
        published = ReviewedMotionBundleStore(self.state).publish(
            self.source.upstream.mesh.project_id,
            self.source.foot,
            self.source.depth,
            artifact.document,
            policy,
            instance,
            self.source.upstream.mesh,
            self.source.upstream.retarget,
        )
        self.verified[
            (published.motion_instance_v2_sha256, published.bundle_sha256)
        ] = SimpleNamespace(
            project_id=published.project_id,
            clip_id=published.clip_id,
            motion_instance_v2_sha256=published.motion_instance_v2_sha256,
            bundle_sha256=published.bundle_sha256,
            foot_lock_candidates_sha256=foot_lock_candidates_sha256(
                self.source.foot
            ),
            depth_order_candidates_sha256=depth_order_candidates_sha256(
                self.source.depth
            ),
            motion_policy_decision_sha256=artifact.sha256,
        )
        return published, artifact.sha256

    @contextmanager
    def exact_reader(self):
        def load(_state, project_id, instance_sha, bundle_sha, _loader):
            value = self.verified.get((instance_sha, bundle_sha))
            if value is None or value.project_id != project_id:
                raise VerifiedReviewedMotionBundleReaderError(
                    "synthetic exact-reader rejection"
                )
            return SimpleNamespace(reviewed_bundle=value)

        with patch(
            "autospine_workbench.idle_behavior_review_packages."
            "load_cached_reviewed_motion_chain",
            new=load,
        ):
            yield

    def list(self):
        with self.exact_reader():
            return list_idle_behavior_review_packages(self.state)

    def get(self, package_id):
        with self.exact_reader():
            return get_idle_behavior_review_address(self.state, package_id)


class IdleBehaviorReviewAddressTests(unittest.TestCase):
    def test_package_id_is_deterministic_and_all_fields_are_bound(self) -> None:
        values = {
            "motion_policy_package_id": "1" * 64,
            "project_id": "project-a",
            "motion_id": "idle-a",
            "clip_id": "clip-a",
            "motion_instance_v2_sha256": "2" * 64,
            "reviewed_motion_bundle_sha256": "3" * 64,
            "p9_decision_sha256": "4" * 64,
        }
        first = IdleBehaviorReviewAddress(**values)
        second = IdleBehaviorReviewAddress(**values)
        self.assertEqual(first.package_id, second.package_id)
        self.assertEqual(first.package_id, IdleBehaviorReviewAddress(
            **first.public_document(),
        ).package_id)
        alternatives = {
            "motion_policy_package_id": "6" * 64,
            "project_id": "project-b",
            "motion_id": "idle-b",
            "clip_id": "clip-b",
            "motion_instance_v2_sha256": "7" * 64,
            "reviewed_motion_bundle_sha256": "8" * 64,
            "p9_decision_sha256": "9" * 64,
        }
        for field, replacement in alternatives.items():
            with self.subTest(field=field):
                changed = IdleBehaviorReviewAddress(
                    **{**values, field: replacement},
                )
                self.assertNotEqual(first.package_id, changed.package_id)

    def test_invalid_address_identity_fails_closed(self) -> None:
        valid = {
            "motion_policy_package_id": "1" * 64,
            "project_id": "project-a",
            "motion_id": "idle-a",
            "clip_id": "clip-a",
            "motion_instance_v2_sha256": "2" * 64,
            "reviewed_motion_bundle_sha256": "3" * 64,
            "p9_decision_sha256": "4" * 64,
        }
        for changes in (
            {"motion_policy_package_id": "not-a-sha"},
            {"project_id": "../escape"},
            {"p9_decision_sha256": "A" * 64},
        ):
            with self.subTest(changes=changes), self.assertRaises(
                IdleBehaviorReviewAddressError,
            ):
                IdleBehaviorReviewAddress(**{**valid, **changes})


class IdleBehaviorReviewPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = _ExactP9Fixture(Path(temporary.name))

    def test_one_real_exact_match_is_recommended_and_path_free(self) -> None:
        published, decision_sha = self.fixture.publish()
        first = self.fixture.list()
        second = self.fixture.list()
        self.assertEqual(first, second)
        self.assertEqual(1, first["count"])
        self.assertEqual(0, first["skipped_count"])
        row = first["packages"][0]
        self.assertEqual(row["package_id"], first["recommended_package_id"])
        self.assertEqual(decision_sha, row["p9_decision_sha256"])
        self.assertNotIn("motion_instance_v2_sha256", row)
        self.assertNotIn("reviewed_motion_bundle_sha256", row)
        encoded = json.dumps(row, ensure_ascii=False)
        self.assertNotIn(published.motion_instance_v2_sha256, encoded)
        self.assertNotIn(published.bundle_sha256, encoded)
        self.assertNotIn(str(self.fixture.root), encoded)

        address = self.fixture.get(row["package_id"])
        self.assertEqual(row["package_id"], address.package_id)
        self.assertEqual(
            published.motion_instance_v2_sha256,
            address.motion_instance_v2_sha256,
        )
        self.assertEqual(
            published.bundle_sha256,
            address.reviewed_motion_bundle_sha256,
        )

    def test_zero_matches_has_no_recommendation(self) -> None:
        result = self.fixture.list()
        self.assertEqual(0, result["count"])
        self.assertEqual([], result["packages"])
        self.assertIsNone(result["recommended_package_id"])

    def test_two_adoptions_for_same_project_and_clip_are_not_recommended(self) -> None:
        first, _first_decision = self.fixture.publish(revision=1)
        second, _second_decision = self.fixture.publish(revision=2)
        self.assertNotEqual(
            first.motion_instance_v2_sha256,
            second.motion_instance_v2_sha256,
        )
        result = self.fixture.list()
        self.assertEqual(2, result["count"])
        self.assertEqual(1, len({
            (row["project_id"], row["clip_id"])
            for row in result["packages"]
        }))
        self.assertIsNone(result["recommended_package_id"])

    def test_invalid_selected_package_id_never_falls_back(self) -> None:
        self.fixture.publish()
        for package_id in ("", "A" * 64, "../" + "a" * 64, "f" * 64):
            with self.subTest(package_id=package_id), self.assertRaises(
                IdleBehaviorReviewPackageError,
            ):
                self.fixture.get(package_id)

    def test_wrong_case_hierarchy_fails_closed(self) -> None:
        state = self.fixture.root / "wrong-case-state"
        state.mkdir()
        (state / "Builds").mkdir()
        with self.assertRaises(IdleBehaviorReviewPackageError):
            list_idle_behavior_review_packages(state)

    def test_bad_bundles_are_skipped_without_hiding_unique_recommendation(self) -> None:
        published, _decision_sha = self.fixture.publish()
        namespace = published.path.parent.parent
        fake = namespace / ("c" * 64) / ("d" * 64)
        missing = namespace / ("e" * 64) / ("f" * 64)
        tampered = namespace / ("1" * 64) / ("2" * 64)
        for target in (fake, missing, tampered):
            shutil.copytree(published.path, target)
        (missing / "reviewed-motion-policy.json").unlink()
        foot = tampered / "foot-lock-candidates.json"
        foot.write_bytes(foot.read_bytes() + b" ")
        result = self.fixture.list()
        self.assertEqual(1, result["count"])
        self.assertEqual(3, result["skipped_count"])
        self.assertEqual(
            result["packages"][0]["package_id"],
            result["recommended_package_id"],
        )


class IdleBehaviorAdoptedRunExactReaderTests(unittest.TestCase):
    def test_cache_seal_failure_is_counted_as_skipped(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = P10PersistedFixture(Path(temporary.name))
        with patch(
            "autospine_workbench.idle_behavior_review_packages."
            "load_cached_reviewed_motion_chain",
            side_effect=IdleBehaviorReviewReplayCacheError("seal rejected"),
        ):
            runs, skipped = _adopted_runs(fixture.state, None)
        self.assertEqual([], runs)
        self.assertEqual(1, skipped)

    def test_invalid_address_manifest_is_counted_as_skipped(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = P10PersistedFixture(Path(temporary.name))
        (fixture.reviewed.path / "run-manifest.json").write_bytes(b"{")
        runs, skipped = _adopted_runs(fixture.state, None)
        self.assertEqual([], runs)
        self.assertEqual(1, skipped)

    def test_fake_missing_and_tampered_bundles_fail_real_exact_discovery(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = P10PersistedFixture(Path(temporary.name))
        valid = fixture.reviewed.path
        namespace = valid.parent.parent
        fake = namespace / valid.parent.name / ("a" * 64)
        missing = namespace / ("b" * 64) / ("c" * 64)
        tampered = namespace / ("d" * 64) / ("e" * 64)
        for target in (fake, missing, tampered):
            shutil.copytree(valid, target)
        (missing / "reviewed-motion-policy.json").unlink()
        depth = tampered / "depth-order-candidates.json"
        depth.write_bytes(depth.read_bytes() + b" ")

        runs, skipped = _adopted_runs(fixture.state, None)
        self.assertEqual(1, len(runs))
        self.assertEqual(fixture.reviewed.bundle_sha256, runs[0].bundle_sha256)
        self.assertEqual(3, skipped)


if __name__ == "__main__":
    unittest.main()
