"""Lazy allow-listed layer source paths for decision revalidation."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any


class LazySourcePaths(Mapping[str, Path]):
    """Resolve only requested known layer ids and memoize strict paths."""

    def __init__(
        self,
        layer_ids: set[str],
        resolver: Callable[[str], Path | None],
    ) -> None:
        self._ids = frozenset(layer_ids)
        self._resolver = resolver
        self._cache: dict[str, Path | None] = {}

    def __getitem__(self, layer_id: str) -> Path:
        if layer_id not in self._ids:
            raise KeyError(layer_id)
        if layer_id not in self._cache:
            value = self._resolver(layer_id)
            self._cache[layer_id] = Path(value) if value is not None else None
        value = self._cache[layer_id]
        if value is None:
            raise KeyError(layer_id)
        return value

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._ids))

    def __len__(self) -> int:
        return len(self._ids)


def project_source_paths(
    project: Mapping[str, Any],
    resolve_asset: Callable[[str, str, str | None], Path],
    missing_error: type[Exception],
) -> LazySourcePaths:
    """Create a lazy map backed by ProjectStore's strict asset resolver."""

    project_id = str(project["id"])

    def resolve(layer_id: str) -> Path | None:
        try:
            return resolve_asset(project_id, "layer", layer_id)
        except missing_error:
            return None

    return LazySourcePaths(
        {str(layer["id"]) for layer in project.get("layers", [])},
        resolve,
    )


def project_override_context(
    project: Mapping[str, Any],
    resolve_asset: Callable[[str, str, str | None], Path],
    missing_error: type[Exception],
) -> dict[str, Any]:
    """Build the immutable project and lazy source context used by the store."""

    return {
        "joint_ids": {item["id"] for item in project["skeleton"]["joints"]},
        "bone_ids": {item["id"] for item in project["skeleton"]["bones"]},
        "layer_ids": {item["id"] for item in project["layers"]},
        "canvas_width": project["canvas"]["width"],
        "canvas_height": project["canvas"]["height"],
        "base_project": project,
        "source_paths": project_source_paths(project, resolve_asset, missing_error),
    }
