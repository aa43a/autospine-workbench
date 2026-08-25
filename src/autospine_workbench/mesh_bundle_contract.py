"""Structural and cross-binding contract for immutable P3 mesh bundles."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .manifest_artifacts import LayerManifestError, require_safe_token, require_sha256
from .mesh_contract import require_mesh_compile_run
from .mesh_visual_artifacts import renderer_identities
from .png_rgba import MAX_RGBA_BYTES, MAX_RGBA_DIMENSION, decode_rgba_png, encode_rgba_png
from .rig_validation import RigSemanticValidator


BUNDLE_ADDRESS_DOMAIN = "autospine-mesh-rig-bundle-address/v1"
DOCUMENT_NAMES = ("rig.json", "run-manifest.json", "probes.json", "visuals.json")
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_TOTAL_JSON_BYTES = 64 * 1024 * 1024
MAX_ARTIFACTS = 1024
MAX_ARTIFACT_PNG_BYTES = MAX_RGBA_BYTES + MAX_RGBA_DIMENSION + 1024 * 1024
MAX_TOTAL_PNG_BYTES = 256 * 1024 * 1024
_VISUAL_KEYS = set("format format_version project_id source renderers status summary images targets artifacts".split())
_TARGET_KEYS = set("attachment_id source_layer_id side proximal_bone_id distal_bone_id".split())
_ARTIFACT_KEYS = set("kind id pose bone angle_deg width height rgba_sha256 png_sha256 path".split())


class MeshBundleContractError(ValueError):
    """Proposed P3 bundle content is not structurally trustworthy."""


@dataclass(frozen=True, slots=True)
class MeshBundleContract:
    project_id: str
    rig_sha256: str
    run_sha256: str
    probes_sha256: str
    visuals_sha256: str
    bundle_sha256: str
    _documents: tuple[tuple[str, bytes], ...] = field(repr=False)
    _pngs: tuple[tuple[str, bytes], ...] = field(repr=False)

    @property
    def document_bytes(self) -> dict[str, bytes]: return dict(self._documents)

    @property
    def png_bytes_by_path(self) -> dict[str, bytes]: return dict(self._pngs)

    @property
    def inventory(self) -> tuple[str, ...]: return tuple(name for name, _ in (*self._documents, *self._pngs))


def build_mesh_bundle_contract(project_id: str, rig: Mapping[str, Any],
                               run: Mapping[str, Any], probes: Mapping[str, Any],
                               visuals: Mapping[str, Any],
                               png_by_path: Mapping[str, bytes]) -> MeshBundleContract:
    """Canonicalize, validate, cross-bind, and snapshot a proposed bundle."""
    try:
        project_id = require_safe_token(project_id, "Project id")
        values = (rig, run, probes, visuals)
        documents = tuple((name, _document(value, name)) for name, value in zip(DOCUMENT_NAMES, values))
        if sum(len(data) for _, data in documents) > MAX_TOTAL_JSON_BYTES:
            raise MeshBundleContractError("mesh bundle JSON resource limit exceeded")
        rig_sha, run_sha, probes_sha, visuals_sha = (_sha(data) for _, data in documents)
        targets = _require_documents(project_id, rig, run, probes, visuals, rig_sha, run_sha, probes_sha)
        pngs, png_shas = _artifacts(visuals, png_by_path, targets)
        bundle_sha = mesh_bundle_address_sha256(
            rig_sha, run_sha, probes_sha, visuals_sha, png_shas
        )
        return MeshBundleContract(project_id, rig_sha, run_sha, probes_sha,
                                  visuals_sha, bundle_sha, documents, pngs)
    except MeshBundleContractError:
        raise
    except (LayerManifestError, RuntimeError, TypeError, ValueError) as exc:
        raise MeshBundleContractError(f"mesh bundle contract failed: {exc}") from exc


def mesh_bundle_address_sha256(rig_sha256: str, run_sha256: str, probes_sha256: str,
                               visuals_sha256: str,
                               artifact_png_sha256s: Mapping[str, str]) -> str:
    """Address four canonical documents and every path-bound artifact PNG."""
    try:
        digests = [require_sha256(value, label) for value, label in (
            (rig_sha256, "Mesh RigIR"), (run_sha256, "Mesh run"),
            (probes_sha256, "Mesh probes"), (visuals_sha256, "Mesh visuals"))]
        if not isinstance(artifact_png_sha256s, Mapping):
            raise MeshBundleContractError("artifact PNG identities must be an object")
        artifacts, folded = [], set()
        for path, digest in artifact_png_sha256s.items():
            _safe_png_path(path)
            if path.casefold() in folded:
                raise MeshBundleContractError("artifact PNG paths are case aliases")
            folded.add(path.casefold())
            artifacts.append({"path": path, "png_sha256": require_sha256(digest, path)})
        payload = {"domain": BUNDLE_ADDRESS_DOMAIN, "rig_sha256": digests[0],
                   "run_sha256": digests[1], "probes_sha256": digests[2], "visuals_sha256": digests[3],
                   "artifacts": sorted(artifacts, key=lambda item: item["path"])}
        return _sha(_canonical(payload))
    except MeshBundleContractError:
        raise
    except (LayerManifestError, TypeError, ValueError) as exc:
        raise MeshBundleContractError("mesh bundle address inputs are invalid") from exc


def _require_documents(project, rig, run, probes, visuals, rig_sha, run_sha, probes_sha):
    require_mesh_compile_run(run)
    RigSemanticValidator(max_influences=2).raise_for_errors(rig)
    if run.get("project_id") != project or (rig.get("qa") or {}).get("status") != "passed":
        raise MeshBundleContractError("mesh project or RigIR QA status is invalid")
    if _object(rig.get("source"), "RigIR source").get("run_manifest_sha256") != run_sha:
        raise MeshBundleContractError("mesh RigIR run binding is invalid")
    _report(probes, "autospine-mesh-action-probes", project,
            {"rig_sha256": rig_sha, "run_manifest_sha256": run_sha}, "probes")
    _report(visuals, "autospine-mesh-visual-artifacts", project,
            {"rig_sha256": rig_sha, "run_manifest_sha256": run_sha,
             "probes_sha256": probes_sha}, "visuals", exact_source=True)
    if set(visuals) != _VISUAL_KEYS or visuals.get("renderers") != renderer_identities():
        raise MeshBundleContractError("mesh visual fields or renderer identities are invalid")
    targets = _targets(visuals.get("targets"))
    _images(visuals.get("images"), targets)
    count = len(targets)
    if visuals.get("summary") != (f"converted={count}" if count else "reviewed-noop"):
        raise MeshBundleContractError("mesh visual summary differs from target count")
    _rig_inventory(rig, targets, run)
    return targets


def _report(document, format_id, project, bindings, label, exact_source=False):
    if not isinstance(document, Mapping) or document.get("format") != format_id or \
            document.get("format_version") != 1 or isinstance(document.get("format_version"), bool) or \
            document.get("project_id") != project or document.get("status") != "passed":
        raise MeshBundleContractError(f"mesh {label} identity, project, or status is invalid")
    source = _object(document.get("source"), f"mesh {label} source")
    if (exact_source and set(source) != set(bindings)) or any(source.get(k) != v for k, v in bindings.items()):
        raise MeshBundleContractError(f"mesh {label} source binding is invalid")


def _targets(value):
    result, source_ids, folded = {}, set(), set()
    for raw in _array(value, "mesh visual targets"):
        item = _object(raw, "mesh visual target")
        if set(item) != _TARGET_KEYS:
            raise MeshBundleContractError("mesh visual target fields are invalid")
        for key in _TARGET_KEYS - {"side"}:
            _safe_id(item.get(key), f"target {key}")
        identifier, side = item["attachment_id"], item.get("side")
        if side not in {"left", "right"} or item["proximal_bone_id"] != f"thigh.{side}" \
                or item["distal_bone_id"] != f"calf.{side}" or identifier.casefold() in folded \
                or item["source_layer_id"] in source_ids:
            raise MeshBundleContractError("mesh visual targets are invalid or duplicated")
        result[identifier], source_ids = item, source_ids | {item["source_layer_id"]}
        folded.add(identifier.casefold())
    if list(result) != sorted(result):
        raise MeshBundleContractError("mesh visual targets must be sorted by id")
    return result


def _images(value, targets):
    ids = []
    for raw in _array(value, "mesh visual images"):
        item = _object(raw, "mesh visual image")
        if set(item) != {"id", "width", "height", "rgba_sha256"}:
            raise MeshBundleContractError("mesh visual image fields are invalid")
        ids.append(_safe_id(item.get("id"), "visual image id"))
        _size(item.get("width"), item.get("height"), "visual image")
        require_sha256(item.get("rgba_sha256"), "Visual image RGBA")
    if ids != sorted(targets) or len(ids) != len(set(ids)):
        raise MeshBundleContractError("mesh visual images must match sorted targets")


def _rig_inventory(rig, targets, run):
    attachments = _array(rig.get("attachments"), "RigIR attachments")
    meshes = {item.get("id"): item for item in attachments
              if isinstance(item, Mapping) and item.get("type") == "mesh"}
    capabilities = (["region_attachment", "mesh_attachment", "setup_draw_order"]
                    if targets else ["region_attachment", "setup_draw_order"])
    if set(meshes) != set(targets) or rig.get("animations") != [] or \
            rig.get("capabilities") != capabilities:
        raise MeshBundleContractError("mesh RigIR inventory or capabilities are invalid")
    vertices = triangles = 0
    for identifier, mesh in meshes.items():
        vertex_rows = _array(mesh.get("vertices"), "mesh vertices")
        tri = _array(mesh.get("triangles"), "mesh triangles")
        if len(vertex_rows) != len(_array(mesh.get("uvs"), "mesh uvs")) or \
                len(vertex_rows) != len(_array(mesh.get("weights"), "mesh weights")) or len(tri) % 3:
            raise MeshBundleContractError("mesh attachment cardinality is invalid")
        allowed = {targets[identifier]["proximal_bone_id"], targets[identifier]["distal_bone_id"]}
        if any(not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or
               any(not isinstance(weight, Mapping) or weight.get("bone") not in allowed for weight in row)
               for row in mesh["weights"]):
            raise MeshBundleContractError("mesh attachment uses a non-target bone")
        vertices += len(vertex_rows)
        triangles += len(tri) // 3
    limits = run["compiler"]["config"]["resource_limits"]
    if vertices > limits["rig_max_vertices"] or triangles > limits["rig_max_triangles"]:
        raise MeshBundleContractError("mesh RigIR exceeds its resource limits")


def _artifacts(visuals, png_by_path, targets):
    raw_items = _array(visuals.get("artifacts"), "mesh visual artifacts")
    if len(raw_items) > MAX_ARTIFACTS or not isinstance(png_by_path, Mapping):
        raise MeshBundleContractError("mesh visual artifact inventory is invalid")
    metadata, paths = {}, []
    for raw in raw_items:
        item = _object(raw, "mesh visual artifact")
        if set(item) != _ARTIFACT_KEYS or item.get("id") not in targets:
            raise MeshBundleContractError("mesh visual artifact fields or target are invalid")
        path = _artifact_shape(item, targets[item["id"]])
        paths.append(path)
        metadata[path] = item
    if paths != sorted(paths) or len({path.casefold() for path in paths}) != len(paths):
        raise MeshBundleContractError("mesh visual artifacts must be path-sorted and unique")
    expected = set(paths)
    if len(paths) != 3 * len(targets) or any(not isinstance(path, str) for path in png_by_path) or \
            len({path.casefold() for path in png_by_path}) != len(png_by_path) or set(png_by_path) != expected:
        raise MeshBundleContractError("mesh visual artifacts and PNG inventory differ")
    return _pngs(paths, metadata, png_by_path)


def _artifact_shape(item, target):
    identifier, pose, angle = item["id"], item.get("pose"), item.get("angle_deg")
    _size(item.get("width"), item.get("height"), "artifact")
    require_sha256(item.get("rgba_sha256"), "Artifact RGBA")
    require_sha256(item.get("png_sha256"), "Artifact PNG")
    if item.get("kind") == "weight_heatmap" and pose == "weights" and \
            item.get("bone") == target["distal_bone_id"] and angle is None:
        expected = f"weights/{identifier}.png"
    elif item.get("kind") == "pose" and pose == "setup" and item.get("bone") is None and angle == 0:
        expected = f"poses/{identifier}.setup.png"
    elif item.get("kind") == "pose" and pose == "widest-safe" and \
            item.get("bone") == target["distal_bone_id"] and type(angle) is int and \
            0 < abs(angle) <= 135 and angle % 5 == 0:
        expected = f"poses/{identifier}.widest-safe-{'p' if angle > 0 else 'm'}{abs(angle):03d}.png"
    else:
        raise MeshBundleContractError("mesh visual artifact pose semantics are invalid")
    if item.get("path") != expected:
        raise MeshBundleContractError("mesh visual artifact path differs from its semantics")
    _safe_png_path(expected)
    return expected


def _pngs(paths, metadata, supplied):
    total, result, identities = 0, [], {}
    for path in paths:
        data = supplied[path]
        if not isinstance(data, bytes):
            raise MeshBundleContractError(f"artifact PNG must be bytes: {path}")
        total += len(data)
        if len(data) > MAX_ARTIFACT_PNG_BYTES or total > MAX_TOTAL_PNG_BYTES:
            raise MeshBundleContractError("artifact PNG resource limit exceeded")
        image = decode_rgba_png(data, source_name=path)
        if encode_rgba_png(image) != data:
            raise MeshBundleContractError(f"artifact PNG is not canonical: {path}")
        item, png_sha = metadata[path], _sha(data)
        if (item["width"], item["height"], item["rgba_sha256"], item["png_sha256"]) != \
                (image.width, image.height, _sha(image.pixels), png_sha):
            raise MeshBundleContractError(f"artifact PNG metadata differs: {path}")
        result.append((path, data))
        identities[path] = png_sha
    return tuple(result), identities


def _safe_png_path(path):
    if not isinstance(path, str) or "\\" in path or path.startswith(("/", ".")):
        raise MeshBundleContractError("artifact PNG path is unsafe")
    parts = path.split("/")
    if len(parts) != 2 or parts[0] not in {"weights", "poses"} or not parts[1].endswith(".png"):
        raise MeshBundleContractError("artifact PNG path is outside weights/ or poses/")
    return path


def _document(value, label):
    if not isinstance(value, Mapping):
        raise MeshBundleContractError(f"{label} must be an object")
    data = _canonical(dict(value))
    if len(data) > MAX_DOCUMENT_BYTES:
        raise MeshBundleContractError(f"{label} exceeds JSON resource limit")
    return data


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value): return hashlib.sha256(value).hexdigest()
def _object(value, label):
    if not isinstance(value, Mapping): raise MeshBundleContractError(f"{label} must be an object")
    return value
def _array(value, label):
    if not isinstance(value, (list, tuple)): raise MeshBundleContractError(f"{label} must be an array")
    return list(value)
def _safe_id(value, label):
    try: return require_safe_token(value, label)
    except LayerManifestError as exc: raise MeshBundleContractError(str(exc)) from exc
def _size(width, height, label):
    if any(type(value) is not int or not 1 <= value <= MAX_RGBA_DIMENSION for value in (width, height)):
        raise MeshBundleContractError(f"{label} dimensions are invalid")
