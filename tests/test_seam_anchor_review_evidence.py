"""Exact candidate-option image evidence tests for P10.5b HTTP."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.seam_anchor_candidate_validation import (  # noqa: E402
    seam_anchor_candidates_sha256,
)
from autospine_workbench.seam_anchor_review_address import (  # noqa: E402
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application_models import (  # noqa: E402
    PreparedSeamAnchorReview,
)
from autospine_workbench.seam_anchor_review_evidence import (  # noqa: E402
    SeamAnchorReviewAttachmentImage,
    SeamAnchorReviewEvidenceError,
    SeamAnchorReviewEvidenceNotFound,
    SeamAnchorReviewEvidenceRepository,
)
from autospine_workbench.seam_anchor_review_history_models import (  # noqa: E402
    SeamAnchorReviewHistorySnapshot,
)
from autospine_workbench.seam_anchor_review_http_models import (  # noqa: E402
    candidate_response,
)
from autospine_workbench.seam_anchor_review_routes import (  # noqa: E402
    dispatch_seam_anchor_review_get,
)
from tests.seam_anchor_review_helpers import review_candidate_and_rig  # noqa: E402


class SeamAnchorReviewEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate, self.rig = review_candidate_and_rig()
        source = self.candidate["source"]
        self.address = ExactSeamAnchorReviewAddress(
            self.candidate["project_id"], source["layer_manifest_sha256"],
            source["rig_sha256"], source["bundle_sha256"],
        )
        digest = seam_anchor_candidates_sha256(self.candidate)
        history = SeamAnchorReviewHistorySnapshot(
            self.address.project_id, digest, 0, 0, None, ()
        )
        self.prepared = PreparedSeamAnchorReview(
            self.address, digest,
            json.dumps(self.candidate, separators=(",", ":")), history,
            400, 400,
        )
        self.images = {}
        for attachment in self.rig["attachments"]:
            raw = b"exact-png:" + attachment["id"].encode("ascii")
            self.images[attachment["id"]] = SimpleNamespace(
                attachment_id=attachment["id"],
                image_sha256=hashlib.sha256(raw).hexdigest(),
                width=attachment["size"][0], height=attachment["size"][1],
                png_bytes=raw,
            )
        self.source = SimpleNamespace(
            rig=self.rig,
            images=tuple(self.images.values()),
            image_by_attachment=dict(self.images),
        )
        self.repository = SeamAnchorReviewEvidenceRepository(ROOT / "unused")

    def load_patch(self, source=None):
        return patch(
            "autospine_workbench.seam_anchor_review_evidence."
            "VerifiedMeshSourceReader.load",
            return_value=self.source if source is None else source,
        )

    def test_projection_is_sorted_complete_path_free_and_url_exact(self):
        with self.load_patch():
            refs = self.repository.attachment_refs(
                self.address, self.prepared
            )
        self.assertEqual(12, len(refs))
        self.assertEqual(12, len({
            (row.option_id, row.attachment_id) for row in refs
        }))
        for index in range(0, len(refs), 2):
            self.assertEqual("parent", refs[index].attachment_role)
            self.assertEqual("child", refs[index + 1].attachment_role)
            self.assertEqual(refs[index].option_id, refs[index + 1].option_id)

        response = candidate_response(self.prepared, refs)
        self.assertEqual(self.candidate, response["candidate"])
        self.assertEqual(400, response["setup_canvas"]["width"])
        self.assertTrue(response["review_assist"][
            "human_confirmation_required"
        ])
        self.assertEqual(self.prepared.candidate_sha256, response[
            "review_assist"
        ]["candidate_sha256"])
        self.assertEqual(12, len(response["attachment_images"]))
        expected = {
            "option_id", "attachment_role", "attachment_id",
            "attachment_type", "image_sha256", "width", "height",
            "canvas_offset_xy", "anchor_points", "url",
        }
        for item in response["attachment_images"]:
            self.assertEqual(expected, set(item))
            self.assertNotIn("path", item)
            self.assertTrue(item["url"].startswith(
                f"/api/projects/{self.address.project_id}/"
                "seam-anchor-reviews/"
            ))
            self.assertIn(f"/options/{item['option_id']}/", item["url"])
            self.assertTrue(item["url"].endswith(item["image_sha256"]))
            self.assertEqual(4, len(item["anchor_points"]))
            self.assertTrue(all(
                0 <= point["x_q1000_px"] <= item["width"] * 1000
                and 0 <= point["y_q1000_px"] <= item["height"] * 1000
                for point in item["anchor_points"]
            ))

    def test_image_requires_candidate_option_attachment_and_digest(self):
        with self.load_patch():
            ref = self.repository.attachment_refs(
                self.address, self.prepared
            )[0]
            image = self.repository.image(
                self.address, self.prepared,
                candidate_sha256=self.prepared.candidate_sha256,
                option_id=ref.option_id, attachment_id=ref.attachment_id,
                image_sha256=ref.image_sha256,
            )
        self.assertEqual(ref.image_sha256, image.image_sha256)
        self.assertEqual(
            self.images[ref.attachment_id].png_bytes, image.png_bytes
        )

        wrong = "a" * 64 if ref.image_sha256 != "a" * 64 else "b" * 64
        attempts = (
            {"candidate_sha256": wrong},
            {"option_id": "seam.not-a-candidate.option.000"},
            {"attachment_id": "not-an-attachment"},
            {"image_sha256": wrong},
        )
        base = {
            "candidate_sha256": self.prepared.candidate_sha256,
            "option_id": ref.option_id,
            "attachment_id": ref.attachment_id,
            "image_sha256": ref.image_sha256,
        }
        for changes in attempts:
            with self.subTest(changes=changes), self.load_patch(), \
                    self.assertRaises(SeamAnchorReviewEvidenceNotFound):
                self.repository.image(
                    self.address, self.prepared, **(base | changes)
                )

    def test_unavailable_option_keeps_images_with_zero_anchor_points(self):
        candidate, rig = review_candidate_and_rig(gap_arm_left=True)
        source = candidate["source"]
        address = ExactSeamAnchorReviewAddress(
            candidate["project_id"], source["layer_manifest_sha256"],
            source["rig_sha256"], source["bundle_sha256"],
        )
        digest = seam_anchor_candidates_sha256(candidate)
        prepared = PreparedSeamAnchorReview(
            address, digest,
            json.dumps(candidate, separators=(",", ":")),
            SeamAnchorReviewHistorySnapshot(
                address.project_id, digest, 0, 0, None, ()
            ),
            400, 400,
        )
        exact_source = SimpleNamespace(
            rig=rig, images=self.source.images,
            image_by_attachment=dict(self.images),
        )
        repository = SeamAnchorReviewEvidenceRepository(ROOT / "unused")
        with patch(
            "autospine_workbench.seam_anchor_review_evidence."
            "VerifiedMeshSourceReader.load",
            return_value=exact_source,
        ):
            refs = repository.attachment_refs(address, prepared)

        option = candidate["relationships"][0]["options"][0]
        self.assertEqual("unavailable", option["status"])
        self.assertEqual([], option["anchors"])
        option_refs = [
            row for row in refs if row.option_id == option["option_id"]
        ]
        self.assertEqual(["parent", "child"], [
            row.attachment_role for row in option_refs
        ])
        self.assertTrue(all(row.anchor_points == () for row in option_refs))
        response_rows = [
            row for row in candidate_response(prepared, refs)[
                "attachment_images"
            ] if row["option_id"] == option["option_id"]
        ]
        self.assertEqual(2, len(response_rows))
        self.assertTrue(all(row["anchor_points"] == []
                            for row in response_rows))

    def test_option_status_anchor_mismatch_fails_closed(self):
        cases = (("candidate", []), ("unavailable", [
            self.candidate["relationships"][0]["options"][0]["anchors"][0]
        ]))
        for status, anchors in cases:
            with self.subTest(status=status):
                forged = json.loads(json.dumps(self.candidate))
                option = forged["relationships"][0]["options"][0]
                option["status"] = status
                option["anchors"] = anchors
                prepared = PreparedSeamAnchorReview(
                    self.address, self.prepared.candidate_sha256,
                    json.dumps(forged, separators=(",", ":")),
                    self.prepared.history, 400, 400,
                )
                with self.load_patch(), self.assertRaises(
                    SeamAnchorReviewEvidenceError
                ):
                    self.repository.attachment_refs(
                        self.address, prepared
                    )

    def test_crosswired_type_and_tampered_bytes_fail_closed(self):
        rig = json.loads(json.dumps(self.rig))
        rig["attachments"][0]["type"] = "mesh" \
            if rig["attachments"][0]["type"] == "region" else "region"
        crosswired = SimpleNamespace(
            rig=rig, images=tuple(self.images.values()),
            image_by_attachment=dict(self.images),
        )
        with self.load_patch(crosswired), self.assertRaises(
            SeamAnchorReviewEvidenceError
        ):
            self.repository.attachment_refs(self.address, self.prepared)

        with self.load_patch():
            ref = self.repository.attachment_refs(
                self.address, self.prepared
            )[0]
        original = self.images[ref.attachment_id]
        tampered_images = dict(self.images)
        tampered_images[ref.attachment_id] = SimpleNamespace(
            attachment_id=original.attachment_id,
            image_sha256=original.image_sha256,
            width=original.width, height=original.height,
            png_bytes=original.png_bytes + b"tampered",
        )
        tampered = SimpleNamespace(
            rig=self.rig, images=tuple(tampered_images.values()),
            image_by_attachment=tampered_images,
        )
        with self.load_patch(tampered), self.assertRaises(
            SeamAnchorReviewEvidenceError
        ):
            self.repository.image(
                self.address, self.prepared,
                candidate_sha256=self.prepared.candidate_sha256,
                option_id=ref.option_id, attachment_id=ref.attachment_id,
                image_sha256=ref.image_sha256,
            )

    def test_exact_image_route_returns_png_etag_without_path(self):
        with self.load_patch():
            ref = self.repository.attachment_refs(
                self.address, self.prepared
            )[0]
        raw = self.images[ref.attachment_id].png_bytes
        parts = [
            "api", "projects", self.address.project_id,
            "seam-anchor-reviews", self.address.layer_manifest_sha256,
            self.address.p3_rig_sha256, self.address.p3_bundle_sha256,
            "candidates", self.prepared.candidate_sha256, "options",
            ref.option_id, "attachments", ref.attachment_id, "images",
            ref.image_sha256,
        ]
        sent_json, sent_bytes = [], []
        store = SimpleNamespace(
            state_root=ROOT / "unused", get_project=lambda _project: {}
        )
        with patch(
            "autospine_workbench.seam_anchor_review_routes."
            "SeamAnchorReviewApplication.prepare",
            return_value=self.prepared,
        ), patch(
            "autospine_workbench.seam_anchor_review_routes."
            "SeamAnchorReviewEvidenceRepository.image",
            return_value=SeamAnchorReviewAttachmentImage(
                ref.image_sha256, ref.width, ref.height, raw
            ),
        ):
            handled = dispatch_seam_anchor_review_get(
                parts, store,
                lambda *values: sent_json.append(values),
                lambda *values: sent_bytes.append(values),
            )
        self.assertTrue(handled)
        self.assertEqual([], sent_json)
        self.assertEqual(1, len(sent_bytes))
        status, body, content_type, headers = sent_bytes[0]
        self.assertEqual((200, raw, "image/png"), (
            int(status), body, content_type,
        ))
        self.assertEqual(f'"{ref.image_sha256}"', headers["ETag"])


if __name__ == "__main__":
    unittest.main()
