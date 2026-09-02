"""Reusable HTTP cases for P10.3c read-only image sessions."""

from autospine_workbench.p10_visual_review_v2_http_security import INTENT


class P10VisualReviewV2ImageSessionHttpCases:
    """Exercise the session boundary through the shared live-server fixture."""

    def mutation_headers(self, intent=INTENT):
        return {
            "Origin": f"http://{self.host}:{self.port}",
            "Sec-Fetch-Site": "same-origin",
            "X-Autospine-Intent": intent,
        }

    def test_read_session_serves_frozen_images_but_never_authorizes_put(self):
        status, _, candidate = self.json_request(
            "GET", f"{self.base}/candidate",
        )
        self.assertEqual(200, status)
        image = (
            f"{self.base}/candidates/{self.candidate_sha}/cases/case-1/"
            f"image/{self.png_sha}?session="
            f"{candidate['image_session']['token']}"
        )
        self.preview.temporary_preview_v2_sha256 = "0" * 64
        status, _, raw = self.request("GET", image)
        self.assertEqual((200, b"PNG"), (status, raw))
        self.assertEqual(1, self.resolve_context.call_count)

        endpoint = f"{self.base}/candidates/{self.candidate_sha}/decisions"
        status, _, value = self.json_request(
            "PUT", endpoint,
            {"candidate_sha256": self.candidate_sha},
            self.mutation_headers(),
        )
        self.assertEqual(409, status)
        self.assertEqual("visual_review_v2_source_changed", value["error"])
        self.service.submit.assert_not_called()
        self.assertEqual([True, False], self.resolve_acceleration)

    def test_unknown_read_session_fails_without_expensive_fallback(self):
        image = (
            f"{self.base}/candidates/{self.candidate_sha}/cases/case-1/"
            f"image/{self.png_sha}?session={'z' * 43}"
        )
        status, _, value = self.json_request("GET", image)
        self.assertEqual(404, status)
        self.assertEqual("visual_review_v2_not_found", value["error"])
        self.resolve_context.assert_not_called()

    def test_noncanonical_encoded_session_key_is_rejected(self):
        image = (
            f"{self.base}/candidates/{self.candidate_sha}/cases/case-1/"
            f"image/{self.png_sha}?sess%69on={'s' * 43}"
        )
        status, _, value = self.json_request("GET", image)
        self.assertEqual(404, status)
        self.assertEqual("visual_review_v2_not_found", value["error"])
        self.resolve_context.assert_not_called()

    def test_crosswired_session_fails_before_current_context_replay(self):
        status, _, candidate = self.json_request(
            "GET", f"{self.base}/candidate",
        )
        self.assertEqual(200, status)
        image = (
            f"{self.base}/candidates/{'0' * 64}/cases/case-1/"
            f"image/{self.png_sha}?session="
            f"{candidate['image_session']['token']}"
        )
        status, _, value = self.json_request("GET", image)
        self.assertEqual(404, status)
        self.assertEqual("visual_review_v2_not_found", value["error"])
        self.assertEqual(1, self.resolve_context.call_count)


__all__ = ["P10VisualReviewV2ImageSessionHttpCases"]
