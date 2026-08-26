"""Single source of truth for admitted MotionIR bundle inventories and budgets."""

from __future__ import annotations

from dataclasses import dataclass

from .bvh_map_validation import MAX_DOCUMENT_BYTES as MAX_BVH_MAP_BYTES
from .bvh_motion_compile_run import MAX_RUN_BYTES as MAX_BVH_RUN_BYTES
from .bvh_tokens import MAX_BVH_BYTES
from .motion_compile_run import MAX_RUN_BYTES
from .motion_validation import MAX_DOCUMENT_BYTES as MAX_MOTION_BYTES


BUILTIN_DOCUMENT_NAMES = ("motion.json", "run-manifest.json")
BVH_DOCUMENT_NAMES = (
    "source.bvh", "map.json", "motion.json", "run-manifest.json",
)
MAX_TOTAL_DOCUMENT_BYTES = MAX_MOTION_BYTES + MAX_RUN_BYTES
MAX_BVH_TOTAL_DOCUMENT_BYTES = (
    MAX_BVH_BYTES + MAX_BVH_MAP_BYTES + MAX_MOTION_BYTES + MAX_BVH_RUN_BYTES
)


class MotionBundleInventoryError(ValueError):
    """Raised when file names, order, bytes, or budgets are not admitted."""


@dataclass(frozen=True, slots=True)
class MotionBundleInventoryProfile:
    """One exact source-kind inventory and its per-file/total ceilings."""

    source_kind: str
    names: tuple[str, ...]
    limits: tuple[int, ...]
    total_limit: int

    @property
    def limit_by_name(self) -> dict[str, int]:
        return dict(zip(self.names, self.limits))


BUILTIN_PROFILE = MotionBundleInventoryProfile(
    "builtin",
    BUILTIN_DOCUMENT_NAMES,
    (MAX_MOTION_BYTES, MAX_RUN_BYTES),
    MAX_TOTAL_DOCUMENT_BYTES,
)
BVH_PROFILE = MotionBundleInventoryProfile(
    "bvh",
    BVH_DOCUMENT_NAMES,
    (MAX_BVH_BYTES, MAX_BVH_MAP_BYTES, MAX_MOTION_BYTES, MAX_BVH_RUN_BYTES),
    MAX_BVH_TOTAL_DOCUMENT_BYTES,
)
PROFILES = (BUILTIN_PROFILE, BVH_PROFILE)


def profile_for_ordered_names(
    names: tuple[str, ...],
) -> MotionBundleInventoryProfile:
    """Resolve only an exact canonical inventory order."""

    for profile in PROFILES:
        if names == profile.names:
            return profile
    raise MotionBundleInventoryError("Motion bundle document inventory is invalid")


def profile_for_file_names(names: set[str]) -> MotionBundleInventoryProfile:
    """Resolve an unordered directory inventory with no missing/extra files."""

    matches = [profile for profile in PROFILES if names == set(profile.names)]
    if len(matches) != 1:
        raise MotionBundleInventoryError("Motion bundle file inventory is invalid")
    return matches[0]


def require_document_items(
    value: tuple[tuple[str, bytes], ...],
    *,
    limit_by_name: dict[str, int] | None = None,
    total_by_kind: dict[str, int] | None = None,
) -> tuple[tuple[str, bytes], ...]:
    """Validate exact order, immutable bytes, and all resource budgets."""

    if type(value) is not tuple:
        raise MotionBundleInventoryError("Motion bundle document inventory is invalid")
    names = tuple(
        item[0] for item in value if type(item) is tuple and len(item) == 2
    )
    profile = profile_for_ordered_names(names)
    limits = profile.limit_by_name
    limits.update(limit_by_name or {})
    total_limit = (total_by_kind or {}).get(
        profile.source_kind, profile.total_limit
    )
    result = []
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            raise MotionBundleInventoryError("Motion bundle document inventory is invalid")
        name, data = item
        if name != profile.names[index] or type(data) is not bytes:
            raise MotionBundleInventoryError("Motion bundle document inventory is invalid")
        if len(data) > limits[name]:
            raise MotionBundleInventoryError(f"{name} exceeds its byte resource limit")
        result.append((name, data))
    if sum(len(data) for _name, data in result) > total_limit:
        raise MotionBundleInventoryError(
            "Motion bundle total byte resource limit exceeded"
        )
    return tuple(result)
