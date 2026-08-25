"""Read-only, exact setup-PNG golden verification."""

from __future__ import annotations

import hashlib
from pathlib import Path
import stat
from typing import Any, Mapping

from .manifest_artifacts import (
    LayerManifestError,
    require_safe_token,
    require_sha256,
)
from .png_rgba import (
    MAX_RGBA_BYTES,
    MAX_RGBA_DIMENSION,
    MAX_RGBA_PIXELS,
    RgbaImage,
    RgbaPngError,
    encode_rgba_png,
    read_rgba_png,
)
from .resolved_project import canonical_sha256
from .rig_bundle_validation import (
    RigBundleError,
    read_json,
)
from .rig_bundle_integrity import verify_rig_bundle_directory
from .rig_setup_artifact import (
    RigSetupArtifactError,
    encoder_identity,
    renderer_identity,
)


MAX_GOLDEN_CONTRACT_BYTES = 64 * 1024
MAX_SETUP_PNG_BYTES = MAX_RGBA_BYTES + 1024 * 1024


class SetupGoldenError(RuntimeError):
    """Raised when a bundle or approved golden cannot be trusted."""

    def __init__(self, message: str, *, code: str = "invalid_input") -> None:
        super().__init__(message)
        self.code = code


def verify_setup_golden(bundle_path: Path, contract_path: Path) -> dict[str, Any]:
    bundle, rig, setup, actual_png = _read_bundle(Path(bundle_path))
    requested = Path(contract_path)
    contract_parent = _safe_directory(requested.parent, "Golden directory")
    contract_path = _exact_child(contract_parent, requested.name)
    try:
        contract = read_json(
            contract_path, max_bytes=MAX_GOLDEN_CONTRACT_BYTES
        )
        _validate_contract(contract)
    except (RigBundleError, RigSetupArtifactError) as exc:
        raise SetupGoldenError("Golden contract is invalid", code="invalid_golden") from exc
    golden_path = _exact_child(contract_path.parent, contract["image"]["path"])
    golden_png = _read_limited(golden_path, MAX_SETUP_PNG_BYTES, "Golden PNG")
    golden = _canonical_image(golden_path, golden_png, "Golden PNG")
    if golden != contract["image"]:
        raise SetupGoldenError(
            "Golden PNG differs from its approved contract", code="invalid_golden"
        )

    rig_sha = canonical_sha256(rig)
    setup_sha = canonical_sha256(setup)
    actual_source = {
        "rig_sha256": rig_sha,
        "bundle_sha256": bundle.name,
        "setup_render_sha256": setup_sha,
    }
    actual_image = dict(setup["image"])
    checks = [
        _check("project.identity", contract["project_id"], setup["project_id"]),
        _check("source.identity", contract["source"], actual_source),
        _check("renderer.identity", contract["renderer"], setup["renderer"]),
        _check("encoder.identity", contract["encoder"], setup["encoder"]),
        _check(
            "image.dimensions",
            [contract["image"]["width"], contract["image"]["height"]],
            [actual_image["width"], actual_image["height"]],
        ),
        _check(
            "image.rgba_sha256",
            contract["image"]["rgba_sha256"],
            actual_image["rgba_sha256"],
        ),
        _check(
            "image.png_sha256",
            contract["image"]["png_sha256"],
            hashlib.sha256(actual_png).hexdigest(),
        ),
    ]
    passed = all(item["status"] == "passed" for item in checks)
    return {
        "format": "autospine-setup-golden-verification",
        "format_version": 1,
        "ok": passed,
        "status": "passed" if passed else "rejected",
        "project_id": setup["project_id"],
        "golden_contract_sha256": canonical_sha256(contract),
        "checks": checks,
    }


def _read_bundle(
    path: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], bytes]:
    parent = _safe_directory(path.parent, "Rig bundle parent")
    bundle = _exact_child(parent, path.name, want_directory=True)
    try:
        verified = verify_rig_bundle_directory(bundle)
    except SetupGoldenError:
        raise
    except (OSError, RigBundleError, RigSetupArtifactError, TypeError, ValueError) as exc:
        raise SetupGoldenError("Rig setup bundle is invalid", code="invalid_bundle") from exc
    return verified.directory, verified.rig, verified.setup, verified.setup_png


def _validate_contract(value: Mapping[str, Any]) -> None:
    _exact(value, {"format", "format_version", "project_id", "source", "renderer", "encoder", "image"}, "golden contract")
    if value.get("format") != "autospine-setup-golden" or value.get("format_version") != 1:
        raise RigSetupArtifactError("Golden contract format is unsupported")
    try:
        require_safe_token(value.get("project_id"), "Project id")
        source = _mapping(value.get("source"), "golden source")
        _exact(source, {"rig_sha256", "bundle_sha256", "setup_render_sha256"}, "golden source")
        for key, digest in source.items():
            require_sha256(digest, key)
        if value.get("renderer") != renderer_identity():
            raise RigSetupArtifactError("Golden renderer identity is unsupported")
        if value.get("encoder") != encoder_identity():
            raise RigSetupArtifactError("Golden encoder identity is unsupported")
        image = _mapping(value.get("image"), "golden image")
        _exact(image, {"path", "width", "height", "rgba_sha256", "png_sha256"}, "golden image")
        filename = require_safe_token(image.get("path"), "Golden image")
        if not filename.lower().endswith(".png"):
            raise RigSetupArtifactError("Golden image must be a PNG filename")
        width, height = _positive_int(image.get("width")), _positive_int(image.get("height"))
        if (
            width > MAX_RGBA_DIMENSION
            or height > MAX_RGBA_DIMENSION
            or width * height > MAX_RGBA_PIXELS
        ):
            raise RigSetupArtifactError("Golden image dimensions exceed the setup limit")
        require_sha256(image.get("rgba_sha256"), "Golden RGBA")
        require_sha256(image.get("png_sha256"), "Golden PNG")
    except LayerManifestError as exc:
        raise RigSetupArtifactError("Golden contract identity is invalid") from exc


def _canonical_image(path: Path, raw: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = read_rgba_png(path)
        canonical = encode_rgba_png(
            RgbaImage(decoded.width, decoded.height, decoded.pixels)
        )
    except RgbaPngError as exc:
        raise SetupGoldenError(f"{label} is not valid RGBA PNG", code="invalid_golden") from exc
    if raw != canonical:
        raise SetupGoldenError(f"{label} is not canonically encoded", code="invalid_golden")
    return {
        "path": path.name,
        "width": decoded.width,
        "height": decoded.height,
        "rgba_sha256": hashlib.sha256(decoded.pixels).hexdigest(),
        "png_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _check(check_id: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "passed" if expected == actual else "rejected",
        "expected": expected,
        "actual": actual,
    }


def _safe_directory(path: Path, label: str) -> Path:
    if _is_alias(path) or not path.is_dir():
        raise SetupGoldenError(f"{label} is not a real directory")
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise SetupGoldenError(f"{label} cannot be resolved") from exc


def _safe_file(path: Path, label: str) -> Path:
    if _is_alias(path) or not path.is_file():
        raise SetupGoldenError(f"{label} is not a regular file")
    return path


def _exact_child(parent: Path, name: str, *, want_directory: bool = False) -> Path:
    try:
        matches = [item for item in parent.iterdir() if item.name.casefold() == name.casefold()]
    except OSError as exc:
        raise SetupGoldenError("Artifact directory cannot be enumerated") from exc
    if len(matches) != 1 or matches[0].name != name:
        raise SetupGoldenError(f"Required artifact is missing or aliased: {name}")
    return (
        _safe_directory(matches[0], name)
        if want_directory
        else _safe_file(matches[0], name)
    )


def _read_limited(path: Path, maximum: int, label: str) -> bytes:
    try:
        with path.open("rb") as handle:
            value = handle.read(maximum + 1)
    except OSError as exc:
        raise SetupGoldenError(f"{label} cannot be read") from exc
    if len(value) > maximum:
        raise SetupGoldenError(f"{label} exceeds its byte limit")
    return value


def _is_alias(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(info.st_mode):
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return True
        except OSError:
            return True
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & flag)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RigSetupArtifactError(f"{label} must be an object")
    return value


def _exact(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise RigSetupArtifactError(f"{label} fields are incomplete or unsupported")


def _positive_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RigSetupArtifactError("Golden dimensions must be positive integers")
    return value
