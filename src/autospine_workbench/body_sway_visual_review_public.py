"""Path-free projections for the public P10.3c review boundary."""

from __future__ import annotations

from typing import Any


def public_visual_review_candidate(value: Any) -> Any:
    """Copy JSON-like candidate data while removing storage path fields."""

    if type(value) is dict:
        return {
            key: public_visual_review_candidate(item)
            for key, item in value.items()
            if key != "path"
        }
    if type(value) is list:
        return [public_visual_review_candidate(item) for item in value]
    return value
