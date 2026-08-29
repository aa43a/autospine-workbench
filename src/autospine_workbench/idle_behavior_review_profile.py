"""Public constants for the P10.0-P10.1 operator review boundary."""

from __future__ import annotations


LIST_FORMAT = "autospine-idle-behavior-review-package-list"
PACKAGE_FORMAT = "autospine-idle-behavior-review-package"
ENTRY_FORMAT = "autospine-idle-behavior-review-entry"
SUBMISSION_FORMAT = "autospine-idle-behavior-review-submission"
RECEIPT_FORMAT = "autospine-idle-behavior-review-receipt"
FORMAT_VERSION = 1
INTENT = "body-sway-human-review-v1"
DECISION_NAMESPACE = "idle-behavior-decisions"
MAX_REVISIONS = 10_000
MAX_PACKAGES = 128
MAX_REQUEST_BYTES = 256 * 1024

TARGET_BONE_IDS = (
    "pelvis-spine",
    "spine-chest",
    "chest-neck",
    "neck-head",
)

SUGGESTED_AMPLITUDES = (0.8, 0.7, 0.4, 0.2)
SUGGESTED_PHASES = (0.0, 0.04, 0.08, 0.12)
