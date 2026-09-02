"""Pure MotionInstance v3 compilation from a P10.6a v2 prepared source."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .motion_instance_v3_prepared_v2 import (
    MotionInstanceV3PreparedV2Error,
    PreparedMotionInstanceV3V2,
)
from .motion_instance_v3_validation_v2 import (
    MotionInstanceV3V2ValidationError,
    expected_motion_instance_v3_document_v2,
    motion_instance_v3_canonical_bytes_v2,
)


class MotionInstanceV3V2CompilerError(ValueError):
    """Raised when an issued v2 source cannot form MotionInstance v3."""


@dataclass(frozen=True, slots=True)
class MotionInstanceV3V2:
    """Frozen canonical v3 payload compiled under the v2 source contract."""

    _canonical_json: str = field(repr=False)

    @property
    def document(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self) -> bytes:
        return self._canonical_json.encode("utf-8")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


def compile_motion_instance_v3_v2(
    prepared: PreparedMotionInstanceV3V2,
) -> MotionInstanceV3V2:
    """Compile and immediately replay exact v2-admitted setup-local data."""

    try:
        document = expected_motion_instance_v3_document_v2(prepared)
        canonical = motion_instance_v3_canonical_bytes_v2(
            document, prepared=prepared,
        )
        return MotionInstanceV3V2(canonical.decode("utf-8"))
    except MotionInstanceV3V2CompilerError:
        raise
    except (
        AttributeError, KeyError, MotionInstanceV3PreparedV2Error,
        MotionInstanceV3V2ValidationError, OverflowError, RecursionError,
        TypeError, UnicodeError, ValueError,
    ) as exc:
        raise MotionInstanceV3V2CompilerError(
            f"MotionInstance v3 v2 compilation failed: {exc}"
        ) from exc


__all__ = [
    "MotionInstanceV3V2", "MotionInstanceV3V2CompilerError",
    "compile_motion_instance_v3_v2",
]
