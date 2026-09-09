"""Live HTTP boundary checks for animated candidate jobs and review edits."""

from unittest.mock import Mock
import unittest

from tests import test_pipeline_web_http as fixture_http
from tests.test_animated_web_jobs import ApplicationDouble
from autospine_workbench.automation.animated_jobs import AnimatedWebJobs


class AnimatedWebHttpTests(unittest.TestCase):
    close_server = fixture_http.PipelineWebHttpTests.close_server
    request = fixture_http.PipelineWebHttpTests.request
    document = fixture_http.PipelineWebHttpTests.document
    terminal = fixture_http.PipelineWebHttpTests.terminal

    def setUp(self):
        fixture_http.PipelineWebHttpTests.setUp(self)
        self.base += "/animated"
        self.application = ApplicationDouble()
        self.application.overview = Mock(return_value={"authority": "none", "review_items": []})
        self.application.review = Mock(return_value={"authority": "none", "review_items": []})
        self.application.complete_bindings = Mock(return_value={"authority": "none"})
        self.application.rig_plan = Mock(return_value={"authority": "none", "status": "missing"})
        self.application.prepare_rig_plan = Mock(return_value={"authority": "none", "status": "ready"})
        self.application.rebase = Mock(return_value={"authority": "none", "joint_review_result": {"changed": True}})
        self.manager._animated = AnimatedWebJobs(self.fixture.fixture.store(), application=self.application)
        self.request_body = {"expected_resolved_sha256": self.request_body["expected_resolved_sha256"],
                             "clip": "limb_diagnostic", "resume": True}

    def test_review_candidate_files_zip_and_head(self):
        status, overview = self.document("GET")
        self.assertEqual(status, 200)
        self.assertEqual(overview["authority"], "none")
        status, job = self.document("POST", "/preview", self.request_body)
        self.assertEqual(status, 202, job)
        result = self.terminal(job)
        self.assertEqual(result["status"], "needs_review")
        suffix = f"/jobs/{job['job_id']}"
        status, headers, raw = self.request("GET", suffix + "/files/skeleton.png")
        self.assertEqual((status, headers["Content-Type"], raw), (200, "image/png", b"PNG"))
        self.assertEqual(self.request("HEAD", suffix + "/files/skeleton.png")[2], b"")
        self.assertEqual(self.request("GET", suffix + "/download")[2][:2], b"PK")
        self.assertEqual(self.request("GET", suffix + "/files/evil.html")[0], 400)
        self.assertEqual(self.request("GET", suffix + "/files/missing.png")[0], 404)
        self.application.stale = True
        self.assertEqual(self.request("GET", suffix + "/download")[0], 409)

    def test_mutation_origin_and_review_bounds(self):
        self.assertEqual(self.request("POST", "/preview", self.request_body,
                                      {"Origin": "http://evil.invalid"})[0], 403)
        body = {"expected_resolved_sha256": "a" * 64, "expected_input_sha256": "b" * 64,
                "records": []}
        self.assertEqual(self.request("POST", "/review", body)[0], 202)
        self.application.review.assert_called_once_with("fixture-project", **body)
        self.assertEqual(self.request("POST", "/review", {**body, "records": [{}] * 257})[0], 400)
        self.assertEqual(self.request("POST", "/review", body, {"X-Autospine-Intent": None})[0], 403)
        self.assertEqual(self.request("GET", "/preview")[0], 405)
        self.assertEqual(self.request("OPTIONS", "/preview")[0], 204)

    def test_rebase_requires_explicit_exact_selection_and_post(self):
        body = {"expected_resolved_sha256": "a" * 64, "expected_registration_sha256": "b" * 64}
        self.assertEqual(self.request("GET", "/rebase")[0], 405)
        self.assertEqual(self.request("POST", "/rebase", {**body, "approve_all": True})[0], 400)
        self.application.rebase.assert_not_called()
        status, response = self.document("POST", "/rebase", body)
        self.assertEqual(status, 202)
        self.assertFalse(response.get("production_authorized", False))
        self.application.rebase.assert_called_once_with("fixture-project", **body)

    def test_completion_is_explicit_candidate_only_post(self):
        body = {"expected_resolved_sha256": "a" * 64, "expected_input_sha256": "b" * 64}
        self.assertEqual(self.request("GET", "/complete-bindings")[0], 405)
        self.assertEqual(self.request("POST", "/complete-bindings", {**body, "approve": True})[0], 400)
        self.assertEqual(self.request("POST", "/complete-bindings", body, {"X-Autospine-Intent": None})[0], 403)
        self.application.complete_bindings.assert_not_called()
        self.assertEqual(self.request("POST", "/complete-bindings", body)[0], 202)
        self.application.complete_bindings.assert_called_once_with("fixture-project", **body)

    def test_rig_plan_get_is_readonly_and_post_checks_intent_and_shape(self):
        body = {"expected_resolved_sha256": "a" * 64, "expected_input_sha256": "b" * 64}
        self.assertEqual(self.request("GET", "/rig-plan")[0], 200)
        self.application.prepare_rig_plan.assert_not_called()
        self.assertEqual(self.request("POST", "/rig-plan", {**body, "approve": True})[0], 400)
        self.assertEqual(self.request("POST", "/rig-plan", body, {"X-Autospine-Intent": None})[0], 403)
        self.application.prepare_rig_plan.assert_not_called()
        self.assertEqual(self.request("POST", "/rig-plan", body)[0], 202)
        self.application.prepare_rig_plan.assert_called_once_with("fixture-project", **body)


if __name__ == "__main__":
    unittest.main()
