"""Build editor import extras from verified, exact region preview sources."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from ..manifest_artifacts import require_safe_token
from ..rig_bundle_integrity import verify_rig_bundle_directory
from ..safe_input_files import strict_json_object
from .region_preview_store import RegionPreviewError, require_sources, safe_path


class EditorImportError(RegionPreviewError):
    """Stable, path-free failures while preparing an editor import package."""

    def __init__(self, reason_code="editor_import_invalid"):
        self.reason_code = reason_code
        super().__init__(reason_code)


def build_editor_files(state_root, project_id, verified_preview_bundle):
    """Return extra ZIP entries; never modify source images or runtime files.

    The caller supplies the result of verify_region_preview. This function reads
    the exact P2 bundle again so atlas reconstruction cannot replace original
    attachment pixels, transparency, dimensions or image identity.
    """
    try:
        return _build(state_root, project_id, verified_preview_bundle)
    except EditorImportError:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError, OSError, AttributeError) as exc:
        raise EditorImportError() from exc


def _build(state_root, project_id, bundle):
    require_safe_token(project_id, "Project id")
    files, addresses = bundle.files, bundle.addresses
    sources = require_sources(addresses["source_addresses"])
    skeleton_bytes = files["skeleton.json"]
    if type(skeleton_bytes) is not bytes or hashlib.sha256(skeleton_bytes).hexdigest() != addresses["skeleton_json_sha256"]:
        raise EditorImportError("editor_import_preview_identity_mismatch")
    source = strict_json_object(files["source.json"], "preview source")
    if source.get("project_id") != project_id or source.get("source_addresses") != sources:
        raise EditorImportError("editor_import_source_mismatch")
    skeleton = strict_json_object(skeleton_bytes, "preview skeleton")
    version = skeleton["skeleton"]["spine"]
    if version not in {"4.2", "4.3.26"}:
        raise EditorImportError("editor_import_target_unsupported")
    rig_path = Path(state_root) / "builds" / project_id / "rig-ir" / sources["rig_sha256"] / sources["rig_bundle_sha256"]
    safe_path(rig_path)
    verified = verify_rig_bundle_directory(rig_path, expected_project_id=project_id)
    rig = verified.rig
    if verified.rig_sha256 != sources["rig_sha256"] or verified.bundle_sha256 != sources["rig_bundle_sha256"] \
            or rig["source"]["layer_manifest_sha256"] != sources["layer_manifest_sha256"] \
            or verified.run["inputs"]["layer_manifest_sha256"] != sources["layer_manifest_sha256"]:
        raise EditorImportError("editor_import_source_mismatch")
    attachments = _rig_attachments(rig)
    _require_skeleton_inventory(skeleton, attachments)
    pngs = verified.region_pngs
    extras = {}
    for name, attachment in sorted(attachments.items()):
        data = pngs[attachment["image_path"]]
        if type(data) is not bytes or hashlib.sha256(data).hexdigest() != attachment["image_sha256"]:
            raise EditorImportError("editor_import_image_identity_mismatch")
        extras[f"editor/images/{name}.png"] = data
    editor = deepcopy(skeleton)
    editor["skeleton"]["images"] = "./images/"
    extras["editor/skeleton.json"] = json.dumps(
        editor, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    extras["editor/README.txt"] = (
        f"Spine {version} 编辑器导入\n\n"
        "1. 完整解压 ZIP，保留 editor/skeleton.json 和 editor/images/ 的相对位置。\n"
        "2. 在对应版本的 Spine 编辑器中选择“导入数据”，打开 editor/skeleton.json。\n"
        "3. 图片路径已设置为 ./images/。若仍显示 MISSING，在图片节点中选择解压后的 editor/images 文件夹。\n"
        "4. 检查角色图层后，另存为自己的 .spine 工程。\n\n"
        "editor/images/ 包含各附件的原始透明 PNG，文件名与 JSON 附件路径对应。\n"
        "ZIP 根目录的 skeleton.json、skeleton.atlas、skeleton.png 用于运行时加载；编辑器请使用本目录的导入文件。\n"
        "此包是经过复核的 region setup 预览，不表示官方 Runtime 认证已经执行。\n"
    ).encode("utf-8")
    return extras


def _rig_attachments(rig):
    result, portable = {}, set()
    for attachment in rig["attachments"]:
        if not isinstance(attachment, dict) or attachment.get("type") != "region":
            raise EditorImportError("editor_import_region_required")
        name = require_safe_token(attachment["id"], "Attachment id")
        if name.casefold() in portable:
            raise EditorImportError("editor_import_attachment_alias")
        portable.add(name.casefold())
        result[name] = attachment
    if not result:
        raise EditorImportError("editor_import_attachment_missing")
    return result


def _require_skeleton_inventory(skeleton, attachments):
    skins = skeleton["skins"]
    if type(skins) is not list:
        raise EditorImportError("editor_import_skeleton_inventory_mismatch")
    seen = set()
    for skin in skins:
        for slot, rows in skin["attachments"].items():
            require_safe_token(slot, "Slot id")
            for name, row in rows.items():
                require_safe_token(name, "Attachment id")
                path = require_safe_token(row.get("path", name), "Attachment path")
                expected = attachments.get(name)
                if expected is None or path != name or row.get("type", "region") != "region" \
                        or expected["slot"] != slot or [row.get("width"), row.get("height")] != expected["size"]:
                    raise EditorImportError("editor_import_skeleton_inventory_mismatch")
                seen.add(path)
    if seen != set(attachments):
        raise EditorImportError("editor_import_skeleton_inventory_mismatch")
