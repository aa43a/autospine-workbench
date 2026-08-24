"""Content-addressed publication for immutable offline analysis artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .resolved_project import canonical_sha256


_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ArtifactStoreError(RuntimeError):
    """Raised when an immutable artifact cannot be safely published."""


@dataclass(frozen=True, slots=True)
class PublishedArtifact:
    path: Path
    sha256: str


class ImmutableJsonArtifactStore:
    def __init__(self, state_root: Path) -> None:
        self.root = Path(state_root) / "analysis"

    def publish(
        self,
        kind: str,
        project_id: str,
        document: Mapping[str, Any],
    ) -> PublishedArtifact:
        for label, value in (("kind", kind), ("project_id", project_id)):
            if not _SAFE_TOKEN.fullmatch(value):
                raise ArtifactStoreError(f"Invalid {label}")
        digest = canonical_sha256(document)
        directory = self.root / project_id / kind
        destination = directory / f"{digest}.json"
        directory.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        if destination.is_file():
            self._verify(destination, digest)
            return PublishedArtifact(destination, digest)

        temp_path: Path | None = None
        try:
            descriptor, raw_temp = tempfile.mkstemp(
                prefix=f".{digest[:12]}.", suffix=".tmp", dir=directory
            )
            temp_path = Path(raw_temp)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, destination)
            except FileExistsError:
                self._verify(destination, digest)
        except (OSError, TypeError, ValueError) as exc:
            raise ArtifactStoreError("Could not publish immutable JSON artifact") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return PublishedArtifact(destination, digest)

    @staticmethod
    def _verify(path: Path, expected_sha256: str) -> None:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            observed = canonical_sha256(document)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ArtifactStoreError("Existing artifact is unreadable") from exc
        if observed != expected_sha256:
            raise ArtifactStoreError("Existing artifact does not match its content address")
