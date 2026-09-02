"""Public, path-free error family for P10.7b v2 runtime job storage."""


class P10Spine42V3RuntimeJobStoreV2Error(RuntimeError):
    """Raised without exposing a local path or private exception."""


class P10Spine42V3RuntimeJobConflictV2(
    P10Spine42V3RuntimeJobStoreV2Error
):
    """Raised when an authorization, retry, or event CAS is stale."""


__all__ = [
    "P10Spine42V3RuntimeJobConflictV2",
    "P10Spine42V3RuntimeJobStoreV2Error",
]
