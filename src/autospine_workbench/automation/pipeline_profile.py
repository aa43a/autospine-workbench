"""Closed, versioned orchestration profiles without implicit release authority."""

from __future__ import annotations

import argparse
import json

SCHEMA = "autospine.pipeline-profile/v1"
PROFILE_NAMES = ("draft_auto", "production_review", "certification_exact")
DEFAULT_PROFILE = "production_review"

# These policies describe intent. They are not runtime or release credentials.
_POLICIES = {
    "draft_auto": ("candidate_preview", "preview_only", "none"),
    "production_review": ("exception_review", "qa_gated", "versioned_policy"),
    "certification_exact": ("exact_replay", "existing_exact_gates", "none"),
}


class PipelineProfileError(ValueError):
    """A stable reason code accompanies every profile rejection."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


def build_pipeline_profile(name: str = DEFAULT_PROFILE) -> dict:
    """Return a fresh immutable-by-convention profile document."""
    if not isinstance(name, str) or name not in _POLICIES:
        raise PipelineProfileError("unsupported_pipeline_profile")
    review, export, adoption = _POLICIES[name]
    return {
        "schema": SCHEMA,
        "profile": name,
        "review_mode": review,
        "export_mode": export,
        "auto_adoption": adoption,
        "artifact_identity": "existing_content_addresses",
        "authority": "none",
    }


def validate_pipeline_profile(document: object) -> dict:
    """Reject extras, policy drift and authority escalation without coercion."""
    if not isinstance(document, dict):
        raise PipelineProfileError("invalid_pipeline_profile")
    expected = build_pipeline_profile(document.get("profile"))
    if document != expected:
        raise PipelineProfileError("pipeline_profile_policy_mismatch")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", default=DEFAULT_PROFILE)
    args = parser.parse_args(argv)
    try:
        document = build_pipeline_profile(args.profile)
    except PipelineProfileError as exc:
        print(json.dumps({"status": "blocked", "reason_code": exc.reason_code}))
        return 2
    print(json.dumps(document, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
