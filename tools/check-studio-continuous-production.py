"""Rebuild two byte-matched authored materials in an isolated workspace/state.

This is an existing-author-input replay, not a new human annotation or visual
acceptance. Only bounded source/authoring closures are restored. No old jobs,
animation builds, Runtime outputs, or stage decisions are transferred.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import traceback
from zipfile import ZipFile

_engine_arguments = argparse.ArgumentParser(add_help=False)
_engine_arguments.add_argument("--engine-root", type=Path)
_selected_engine, _ = _engine_arguments.parse_known_args()
ENGINE = (_selected_engine.engine_root or Path(__file__).resolve().parents[1]).absolute()
sys.path.insert(0, str(ENGINE / "src"))
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.automation.storage_io import canonical_bytes

SHA = re.compile(r"[a-f0-9]{64}")
MAX_FILE = 64 << 20
MAX_CLOSURE = 128 << 20
MAX_FILES = 512
CASES = {
    "molisha": dict(
        psd_sha256="33cd19e7d6721e5cc1f4e1474a928bda88a1d55217efcc3880dcb90d0a2c995e",
        dataset="project-audit-a30bbe4015221e579cccc5fd",
        bundle="9afcf3b4117dc8fd805d2553e61d0fb5d6e848085964d9c6c2ef7189327f03a4",
        assisted="0fed53abfdd2039a0554043fb9d6629f7101cd66f9ed83da804b363e193936e7",
        draft="363ab61616646088ee73c72df75ee903af8b8dc19c405e88ef8989075c8f5a94",
        registration_revision=8, route="ordinary",
        skirt_texture="e84d1616c5a716873397e843ccd457f9eac045b1697c21f7ef38fbf313ba418d",
    ),
    "paqiuli": dict(
        psd_sha256="68d610c9586abfede03924c964a1d0a233f4d369570eb7d691635c8c09e58700",
        dataset="project-audit-22b143dcd81cbd7dd30f6588",
        bundle="67bfafafaaa52bd459756d3e20fae3387bd69f70f3007d7cb50827811ff671c2",
        assisted="1cd5912c86c440f1eda3f2c6e8b9c879405e50920ddc517fe604c492c8270d5a",
        draft="37ad1b7ee271ce68a4627453cd4575f1398b6db8b303aa2a280b29221745178a",
        registration_revision=5, route="sleeves",
        sleeve_revision=5,
        sleeve_draft="b6d7847e62ba8c9c7d0758aa883d10deced63865695642393c77b54d19e5fb8b",
        skirt_texture="b732f70b8c1e7224112a9a4d016fdbf5d35f25a09b2bc5e1727a489cb7e1a886",
    ),
}
REPORT_KINDS = frozenset({
    "assisted-joint-drafts", "assisted-skeleton-candidates", "joint-baselines",
    "layer-binding-candidates-v2", "layer-binding-drafts-v2", "project-input-sources",
    "rig-plans-v1", "semantic-audits", "semantic-candidates", "simple-binding-decisions-v1",
})
SOURCE_FBX = "motion-2671c6fdbc10444592420e6f8f4ad838"
SOURCE_FBX_SHA = "67bf8b91cb77fec8873bb059cddcb96198c9ca348a16cfa6eb60171dabbd5370"
CAPTURE_MANIFEST_SHA = "ec69a82c3a280665fb560f4cbdd567660570c9a6021d3cf29db54b6a6511b99b"
BLENDER_MANIFEST_SHA = "5ba1a63e8fdf201bafff0fc2f399b155cc5d9c4f31605b440b89a00600fcc830"
CORE_MANIFEST_SHA = "ca0dbf9b1c04d002962824d249bb421451bc0b3b8418e095f30cae8bca128ea6"
FROZEN_RELEASES = {CORE_MANIFEST_SHA: dict(source_commit_prefix="97078e", files=3279)}
ORIGINAL_PAQIULI_CHARACTER = "481e0e2dd523f82bf3c462c9e260f5cc77fd047b0c10af25fa26ef3808bd1294"
PAQIULI_RESIDUALS = {
    "layer-003-unbound-residual": "fc5642a8ca6fd474c9290cb6abf8e83b72c4b84a11f397e29d839e29dad57dc6",
    "layer-004-unbound-residual": "31043debcb04126b88dc7f40b11c67117e78bbf06c75b673b6e9ccd9ac17652a",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def real_path(path: Path, root: Path, *, file=True, maximum=MAX_FILE, minimum=1):
    """Reject links/reparse points before resolving; validate every ancestor."""
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    require(path.is_relative_to(root), "source_outside_root")
    for current in reversed((path, *path.parents)):
        info = current.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "source_alias")
        if current == path and file:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "source_not_real_file")
            require(minimum <= info.st_size <= maximum, "source_file_limit")
        else:
            require(stat.S_ISDIR(info.st_mode), "source_not_directory")
    return path


def identity(path):
    value = path.lstat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


def fingerprint(path, root, maximum=MAX_FILE, *, minimum=1):
    path = real_path(path, root, maximum=maximum, minimum=minimum)
    before = identity(path)
    digest = sha256()
    with path.open("rb") as handle:
        for raw in iter(lambda: handle.read(1 << 20), b""):
            digest.update(raw)
    real_path(path, root, maximum=maximum, minimum=minimum)
    require(identity(path) == before, "source_changed_during_read")
    return dict(bytes=before[2], sha256=digest.hexdigest())


def read_json(path, root, maximum=16 << 20):
    expected = fingerprint(path, root, maximum)
    raw = path.read_bytes()
    require(len(raw) == expected["bytes"] and sha256(raw).hexdigest() == expected["sha256"],
            "source_changed_during_read")
    value = json.loads(raw)
    require(type(value) is dict, "source_json_object_required")
    return value


def restore_target_allowed(relative, case):
    p = PurePosixPath(relative)
    if (not relative or "\\" in relative or ":" in relative or p.is_absolute()
            or p.as_posix() != relative
            or any(part in (".", "..") for part in relative.split("/"))):
        return False
    parts = p.parts
    project = "imported-" + case["psd_sha256"]
    hashed = lambda name: bool(re.fullmatch(r"[a-f0-9]{64}\.json", name))
    if len(parts) == 4 and parts[:2] == ("benchmarks", case["dataset"]):
        return parts[2] in REPORT_KINDS and hashed(parts[3])
    if len(parts) == 4 and parts[:3] == ("analysis", project, "benchmark-pose-observations"):
        return hashed(parts[3])
    if len(parts) == 3 and parts[:2] == ("animation-inputs", project):
        return bool(re.fullmatch(r"\d{6}\.json", parts[2]))
    if parts[:3] == ("input-preparation", "source-bundles", case["bundle"]):
        return (len(parts) == 4 and parts[3] in ("inventory.json", "audit.json", "composite.png")
                or len(parts) == 5 and parts[3] == "layers"
                and bool(re.fullmatch(r"layer-\d{3}\.png", parts[4])))
    if case["route"] == "sleeves":
        if len(parts) == 3 and parts[:2] in (("sleeve-onboarding-v1", project), ("project-route-v1", project)):
            return bool(re.fullmatch(r"revision-\d{12}\.json", parts[2]))
        if len(parts) == 4 and parts[:3] == ("benchmarks", "project-component-partitions", "weighted-mesh-candidates"):
            return hashed(parts[3])
    return False


class ClosurePlan:
    def __init__(self, state, case):
        self.state, self.case, self.files = state, case, {}

    def add(self, relative, expected=None, *, document_digest=False):
        require(restore_target_allowed(relative, self.case), "restore_target_forbidden")
        path = self.state / relative
        info = fingerprint(path, self.state)
        if expected is not None:
            require(info["sha256"] == expected, "source_digest_mismatch")
        if document_digest:
            doc = read_json(path, self.state)
            require(canonical_sha256(doc) == path.stem and doc.get("authority") == "none",
                    "author_document_digest_mismatch")
            require(doc.get("production_authorized", False) is False, "author_document_authorized")
        self.files[relative] = dict(info, source=str(path), target=relative)
        require(len(self.files) <= MAX_FILES and sum(v["bytes"] for v in self.files.values()) <= MAX_CLOSURE,
                "author_closure_limit")

    def rows(self):
        return [self.files[key] for key in sorted(self.files)]

    def check_unchanged(self):
        for item in self.rows():
            require(fingerprint(Path(item["source"]), self.state) ==
                    {key: item[key] for key in ("bytes", "sha256")}, "source_inventory_changed")


def sha_strings(value):
    if isinstance(value, str) and SHA.fullmatch(value):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from sha_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from sha_strings(item)


def build_author_plan(projects, name):
    """Read/replay fixed sources without acquiring a writable authoring lock."""
    from autospine_workbench.automation.animated_inputs import load_inputs, _registrations
    from autospine_workbench.automation.input_preparation_sources import SourceStore
    from autospine_workbench.automation.sleeve_onboarding import SleeveOnboarding
    from autospine_workbench.benchmark.joint_draft import JOINTS

    case, state = CASES[name], projects.state_root
    project = "imported-" + case["psd_sha256"]
    project_doc = projects.get_project(project)
    require(project_doc["overrides"]["revision"] == 0, "author_override_restore_not_supported")
    registrations = _registrations(projects, project)
    latest = registrations[-1][1]
    require(latest["revision"] == case["registration_revision"]
            and latest["source_draft_sha256"] == case["draft"], "pinned_author_registration_changed")
    require(latest["manifest"]["source_bundle_sha256"] == case["bundle"]
            and latest["manifest"]["dataset_id"] == case["dataset"], "pinned_source_changed")
    with load_inputs(projects, project) as inputs:
        require(canonical_sha256(inputs.assisted) == case["assisted"], "pinned_author_joints_changed")
        require(set(inputs.assisted["reviewed_joint_ids"]) == set(JOINTS)
                and len(inputs.assisted["reviewed_joint_ids"]) == 17, "author_joint_review_incomplete")
        require(inputs.assisted["annotation_mode"] == "model_assisted"
                and inputs.assisted["independent_annotation"] is False, "author_joint_provenance_changed")
        provenance = dict(project_id=project, source_addresses=inputs.source_addresses,
                          annotation_mode="model_assisted", independent_annotation=False,
                          reviewed_joint_ids=inputs.assisted["reviewed_joint_ids"],
                          assisted_sha256=case["assisted"], checkpoint=latest["checkpoint"],
                          origin="original_user_saved_input_not_new_review")
        inputs.assert_current()
    plan = ClosurePlan(state, case)
    for _, registration in registrations:
        plan.add(f"animation-inputs/{project}/{registration['revision']:06d}.json")
    dataset = state / "benchmarks" / case["dataset"]
    for kind in REPORT_KINDS:
        folder = dataset / kind
        if not folder.exists():
            continue
        real_path(folder, state, file=False)
        for path in sorted(folder.glob("*.json")):
            plan.add(path.relative_to(state).as_posix(), document_digest=True)
    pose = inputs.assisted["source_pose_sha256"]
    plan.add(f"analysis/{project}/benchmark-pose-observations/{pose}.json")
    source = SourceStore(state).read(case["bundle"])
    bundle_root = f"input-preparation/source-bundles/{case['bundle']}"
    plan.add(bundle_root + "/inventory.json")
    for relative, raw in source.items():
        plan.add(bundle_root + "/" + relative, sha256(raw).hexdigest())
    if case["route"] == "sleeves":
        service = SleeveOnboarding(projects)
        value = service._latest(project)
        require(value["revision"] == case["sleeve_revision"] and value["saved"]
                and value["draft_sha256"] == case["sleeve_draft"], "pinned_sleeve_input_changed")
        require(value["input_addresses"] == provenance["source_addresses"], "sleeve_author_source_changed")
        service._saved_reuse(value)
        _, _, _, draft = service._read_documents(value)
        provenance["sleeves"] = dict(revision=value["revision"], draft_sha256=value["draft_sha256"],
            origin_counts=dict(Counter(a["origin"] for r in draft["records"] for a in r["assignments"])),
            records=[dict(layer_id=r["layer_id"], component_id=r["component_id"],
                          assignment_count=len(r["assignments"])) for r in draft["records"]],
            motion_review_reused=False)
        pending = set()
        for revision in range(1, value["revision"] + 1):
            relative = f"sleeve-onboarding-v1/{project}/revision-{revision:012d}.json"
            plan.add(relative)
            pending.update(sha_strings(read_json(state / relative, state)))
        mesh_root = state / "benchmarks/project-component-partitions/weighted-mesh-candidates"
        visited = set()
        while pending:
            digest = pending.pop()
            if digest in visited:
                continue
            visited.add(digest)
            path = mesh_root / (digest + ".json")
            if path.exists():
                plan.add(path.relative_to(state).as_posix(), document_digest=True)
                pending.update(sha_strings(read_json(path, state)))
        route = f"project-route-v1/{project}/revision-000000000001.json"
        doc = read_json(state / route, state)
        require(doc["choice"] == "sleeves" and doc["source_sha256"] == latest["checkpoint"]["resolved_project_sha256"],
                "sleeve_route_changed")
        plan.add(route)
    plan.check_unchanged()
    provenance["closure_sha256"] = canonical_sha256(plan.rows())
    return plan, provenance


def copy_author_closure(plan, destination):
    """Exclusive byte-for-byte restore of the declared source input inventory."""
    require(not (destination / "jobs").exists(), "old_jobs_present_before_author_restore")
    plan.check_unchanged()
    for item in plan.rows():
        require(restore_target_allowed(item["target"], plan.case), "restore_target_forbidden")
        path = destination / item["target"]
        path.parent.mkdir(parents=True, exist_ok=True)
        real_path(path.parent, destination, file=False)
        source = real_path(Path(item["source"]), plan.state)
        before = identity(source)
        digest = sha256()
        with source.open("rb") as handle, path.open("xb") as target:
            for raw in iter(lambda: handle.read(1 << 20), b""):
                digest.update(raw)
                target.write(raw)
            target.flush()
            os.fsync(target.fileno())
        require(digest.hexdigest() == item["sha256"] and identity(source) == before,
                "source_changed_during_restore")
        require(fingerprint(path, destination) == {k: item[k] for k in ("bytes", "sha256")},
                "restored_author_input_changed")
    plan.check_unchanged()


def reserve_output(path, source_state, source_audit):
    path = Path(os.path.abspath(path))
    require(not path.is_relative_to(source_state) and not path.is_relative_to(source_audit), "output_overlaps_source")
    if path.exists():
        real_path(path, path, file=False)
        require(not any(path.iterdir()), "output_not_empty")
    else:
        ancestor = path.parent
        while not ancestor.exists():
            ancestor = ancestor.parent
        real_path(ancestor, ancestor, file=False)
        path.mkdir(parents=True)
        real_path(path, path, file=False)
    return path


def require_completed_owned_report(report):
    require(report.get("ok") is True
            and report.get("schema") == "autospine.studio-continuous-production-test/v1"
            and report.get("scope") == "existing-author-input-replay"
            and report.get("status") == "new_candidates_exported_needs_review"
            and report.get("human_visual_acceptance") is False
            and report.get("source_state_written") is False
            and report.get("frozen_engine_source_unchanged") is True,
            "only_completed_owned_run_may_resume")


def write_report(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    temporary = path.with_suffix(".pending")
    with temporary.open("wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def wait_task(read, done, timeout, *, label, progress_path=None):
    end, previous = time.monotonic() + timeout, None
    while time.monotonic() < end:
        value = read()
        progress = (value.get("status"), value.get("step"), value.get("reason_code"),
                    tuple((k, v.get("status")) for k, v in value.get("stages", {}).items()))
        if progress != previous:
            current = dict(task=label, status=progress[0], step=progress[1], reason=progress[2],
                           stages=dict(progress[3]))
            print(json.dumps(current), flush=True)
            if progress_path is not None:
                write_report(progress_path, current)
            previous = progress
        if done(value):
            return value
        time.sleep(2)
    raise TimeoutError("continuous_production_timeout:" + label)


@contextmanager
def runtime_environment(blender, capture):
    values = dict(AUTOSPINE_BLENDER=str(blender),
                  AUTOSPINE_CAPTURE_DEPENDENCIES=str(capture / "dependencies"),
                  AUTOSPINE_CAPTURE_BROWSER=str(capture / "browser/chrome-headless-shell.exe"),
                  AUTOSPINE_CAPTURE_NODE=str(capture / "node/node.exe"),
                  PYTHONPATH=str(ENGINE / "src"), PYTHONDONTWRITEBYTECODE="1")
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def production_settings():
    from autospine_workbench.targets.character43.joint_animation_config import defaults
    from autospine_workbench.automation.motion_camera_policy import PROFILE, ANKLE_PROFILE
    config = defaults()
    config["face"].update(enabled=True)
    config["hair"].update(enabled=True, max_angle=3)
    config["cloth"].update(enabled=True, max_angle=2)
    config["objects"].update(enabled=False)
    return dict(contact_correction=False, pose_profile=PROFILE, moving_ankle_profile=ANKLE_PROFILE,
                projection=dict(profile=PROFILE, keys=[dict(time=0, yaw=0)])), config


def production_request(project, source_job, body, joint, skirt_profile=None):
    request = dict(project_id=project, character_job_id=None, source_job_id=source_job,
                   body_options=body, joint_config=joint)
    if skirt_profile is not None:
        require(skirt_profile == "reviewed-torso-waist-v2", "fixture_character_profile_invalid")
        request["character_options"] = dict(skirt_profile=skirt_profile)
    return request


def distribution_snapshot(root, filename, digest, schema, profile_key, profile, count):
    """Read the fixed release and reject undeclared files, aliases, and mutation."""
    manifest_path = root / filename
    expected = fingerprint(manifest_path, root)
    require(expected["sha256"] == digest, "runtime_manifest_not_fixed_release")
    manifest = read_json(manifest_path, root)
    require(manifest.get("schema") == schema and manifest.get(profile_key) == profile, "runtime_bundle_invalid")
    require(type(manifest.get("files")) is list and len(manifest["files"]) == count, "runtime_inventory_invalid")
    result = {filename: expected}
    for row in manifest["files"]:
        relative = row["path"]
        path = PurePosixPath(relative)
        require(path.as_posix() == relative and not path.is_absolute() and ".." not in path.parts
                and "\\" not in relative and ":" not in relative and relative not in result, "runtime_path_invalid")
        info = fingerprint(root / relative, root, maximum=256 << 20, minimum=0)
        require(info == {k: row[k] for k in ("bytes", "sha256")}, "runtime_bundle_digest_mismatch")
        result[relative] = info
    actual = set()
    for folder, directories, files in os.walk(root):
        real_path(Path(folder), root, file=False)
        for directory in directories:
            real_path(Path(folder) / directory, root, file=False)
        for filename in files:
            actual.add((Path(folder) / filename).relative_to(root).as_posix())
            require(len(actual) <= count + 1, "runtime_inventory_invalid")
    require(actual == set(result), "runtime_inventory_unlisted_file")
    return result


def capture_snapshot(capture):
    return distribution_snapshot(capture, "capture-distribution.json", CAPTURE_MANIFEST_SHA,
        "autospine.capture-runtime-distribution/v1", "capture_profile", "official-webgl-swiftshader-native-v1", 840)


def blender_snapshot(blender_root):
    return distribution_snapshot(blender_root, "blender-distribution.json", BLENDER_MANIFEST_SHA,
        "autospine.blender-runtime-distribution/v1", "conversion_profile", "blender-5.2.1-isolated-task-v1", 6528)


def engine_source_snapshot(expected_manifest_sha256=CORE_MANIFEST_SHA):
    distribution = ENGINE.parent
    path = distribution / "engine-distribution.json"
    manifest = read_json(path, distribution)
    manifest_info = fingerprint(path, distribution)
    fixed = FROZEN_RELEASES.get(expected_manifest_sha256)
    require(fixed is not None and manifest_info["sha256"] == expected_manifest_sha256
            and manifest["engine_root"] == "engine"
            and manifest["source_commit"].startswith(fixed["source_commit_prefix"]),
            "engine_not_explicit_fixed_release")
    rows = [row for row in manifest["files"] if row["path"].startswith("engine/")]
    require(len(rows) == fixed["files"], "engine_source_inventory_invalid")
    result = {}
    for row in rows:
        relative = row["path"][7:]
        parsed = PurePosixPath(relative)
        require(parsed.as_posix() == relative and not parsed.is_absolute()
                and ".." not in parsed.parts and "\\" not in relative and ":" not in relative
                and relative not in result, "engine_source_path_invalid")
        info = fingerprint(ENGINE / relative, ENGINE, minimum=0)
        require(info == {key: row[key] for key in ("bytes", "sha256")}, "engine_source_digest_mismatch")
        result[relative] = info
    actual = set()
    for folder, directories, files in os.walk(ENGINE):
        real_path(Path(folder), ENGINE, file=False)
        for directory in directories:
            real_path(Path(folder) / directory, ENGINE, file=False)
        for filename in files:
            actual.add((Path(folder) / filename).relative_to(ENGINE).as_posix())
            require(len(actual) <= fixed["files"], "engine_source_inventory_invalid")
    require(actual == set(result), "engine_source_unlisted_file")
    return dict(engine_root=str(ENGINE), manifest_sha256=manifest_info["sha256"],
                source_commit=manifest["source_commit"], files=len(rows),
                bytes=sum(row["bytes"] for row in rows),
                inventory_sha256=canonical_sha256(result))


def earwear_context(files, resolved_sha256):
    """Same authored head decoration; never generalize this fixed replay rule."""
    manifest = json.loads(files["character-manifest.json"])
    require(manifest["source_addresses"]["resolved_project_sha256"] == resolved_sha256,
            "earwear_source_context_changed")
    layer = [row for row in manifest["layers"] if row["layer_id"] == "layer-005"]
    require(len(layer) == 1 and layer[0]["name"] == "earwear"
            and layer[0]["state"] == "static_reference"
            and layer[0]["regions"] == [dict(region_id="layer-005", state="static_reference")]
            and not layer[0]["missing_region_ids"], "earwear_region_context_changed")
    texture = sha256(files["images/layer-005.png"]).hexdigest()
    require(texture == "8bb562d48c409b73640e9d6151f76d61e4844dcec5620b716164ee011f3f4dae",
            "earwear_texture_changed")
    skeleton = json.loads(files["skeleton.json"])
    require("head" in {bone["name"] for bone in skeleton["bones"]}, "earwear_parent_unavailable")
    return dict(layer_id="layer-005", region_id="layer-005", parent="head", name="earwear",
                texture_sha256=texture, resolved_project_sha256=resolved_sha256)


def skirt_context(files, name, resolved_sha256):
    manifest = json.loads(files["character-manifest.json"])
    require(manifest["source_addresses"]["resolved_project_sha256"] == resolved_sha256,
            "skirt_source_context_changed")
    layer = [row for row in manifest["layers"] if row["layer_id"] == "layer-006"]
    require(len(layer) == 1 and layer[0]["name"] == "bottomwear"
            and layer[0]["state"] == "static_reference"
            and layer[0]["regions"] == [dict(region_id="layer-006", state="static_reference")]
            and not layer[0]["missing_region_ids"], "skirt_region_context_changed")
    texture = sha256(files["images/layer-006.png"]).hexdigest()
    require(texture == CASES[name]["skirt_texture"], "skirt_texture_changed")
    skeleton = json.loads(files["skeleton.json"])
    require({"chest", "pelvis"} <= {bone["name"] for bone in skeleton["bones"]}, "skirt_anchors_unavailable")
    return dict(layer_id="layer-006", region_id="layer-006", name="bottomwear",
                texture_sha256=texture, resolved_project_sha256=resolved_sha256,
                profile="reviewed-torso-waist-v2", origin="new_agent_strategy_selection")


def original_residual_files(source_projects):
    """Read only old manifest/texture evidence; never restore this old candidate."""
    root = source_projects.state_root / "builds/animated-preview-v1" / ORIGINAL_PAQIULI_CHARACTER
    inventory = read_json(root / "inventory.json", source_projects.state_root)
    require(canonical_sha256(inventory) == ORIGINAL_PAQIULI_CHARACTER,
            "original_residual_inventory_changed")
    names = ["character-manifest.json", *["images/" + key + ".png" for key in PAQIULI_RESIDUALS]]
    files = {}
    for name in names:
        info = fingerprint(root / name, source_projects.state_root)
        require(info["sha256"] == inventory[name], "original_residual_evidence_changed")
        files[name] = (root / name).read_bytes()
        require(sha256(files[name]).hexdigest() == info["sha256"], "original_residual_evidence_changed")
    return files, dict(artifact_sha256=ORIGINAL_PAQIULI_CHARACTER,
                       manifest_sha256=inventory["character-manifest.json"],
                       read_only=True, old_candidate_transferred=False)


def residual_retention_evidence(original, initial, final, source_addresses, coverage):
    """Only the exact two original sleeve residuals may remain unresolved."""
    manifests = [json.loads(files["character-manifest.json"]) for files in (original, initial, final)]
    for manifest in manifests:
        require(manifest.get("authority") == "none" and manifest.get("production_authorized") is False
                and all(manifest["source_addresses"].get(key) == value for key, value in source_addresses.items()),
                "retained_residual_source_changed")
    unresolved = sorted(region["region_id"] for layer in coverage["layers"] if layer["unresolved"]
                        for region in layer["regions"] if region["state"] == "static_reference")
    require(unresolved == sorted(PAQIULI_RESIDUALS) and coverage["unresolved_layer_count"] == 2
            and not any(layer["missing_region_ids"] for layer in coverage["layers"]),
            "other_unresolved_character_regions")
    rows = []
    for region, digest in PAQIULI_RESIDUALS.items():
        layer_id, filename = region[:9], "images/" + region + ".png"
        for manifest in manifests:
            layer = [item for item in manifest["layers"] if item["layer_id"] == layer_id]
            require(len(layer) == 1 and dict(region_id=region, state="static_reference") in layer[0]["regions"]
                    and any(r["state"] == "weighted_candidate" for r in layer[0]["regions"]),
                    "retained_residual_region_changed")
        identities = [sha256(files[filename]).hexdigest() for files in (original, initial, final)]
        require(identities == [digest] * 3, "retained_residual_texture_changed")
        rows.append(dict(region_id=region, layer_id=layer_id, state="static_reference",
                         texture_path=filename, texture_sha256=digest, original_texture_sha256=identities[0],
                         initial_texture_sha256=identities[1], final_texture_sha256=identities[2], byte_matched=True))
    return dict(scope="retained_original_sleeve_residuals_only", verified=True,
                original_character_artifact_sha256=ORIGINAL_PAQIULI_CHARACTER,
                source_addresses=source_addresses, regions=rows, other_unresolved_region_ids=[],
                complete_character_coverage=False, excluded=False, human_acceptance_transferred=False)


def technical_statistics(review, archive):
    """Count actual exported evidence, retaining failures and missing coverage."""
    with ZipFile(archive) as bundle:
        deformation = json.loads(bundle.read("deformation.json"))
        depth = json.loads(bundle.read("motion-depth.json"))
        motion = json.loads(bundle.read("motion-review.json"))
    records = deformation["records"]
    stages = review["readiness"]["stages"]
    overlap = depth.get("target_overlap", {})
    return dict(scope="implemented_technical_evidence_not_visual_acceptance",
        readiness_status=review["readiness"]["status"],
        geometry=dict(passed=deformation["passed"], record_count=len(records),
            failing_records=sum(row["passed"] is False for row in records),
            generic_failing_records=sum(row.get("generic_geometry_passed") is False for row in records),
            failing_attachment_frame_samples=sum(row["failing_frame_count"] for row in records),
            failing_frame_count_scope="generic_record_counter_not_semantic_pass_boolean",
            inversion_samples=sum(row["inversion_samples"] for row in records),
            sample_counts=sorted({row["sample_count"] for row in records})),
        runtime=[dict(status=row["status"], frames=row.get("frames")) for row in stages if row["stage"] == "Runtime"],
        depth=dict(status=depth["status"], ambiguous_pair_samples=depth.get("ambiguous_pair_samples"),
            unmeasured_pair_samples=overlap.get("unmeasured_pair_samples"),
            order_mismatch_pair_samples=overlap.get("order_mismatch_pair_samples"),
            visible_pair_samples=overlap.get("visible_pair_samples")),
        unmeasured_stages=[row["stage"] for row in stages if row["status"] == "unmeasured"],
        needs_changes_stages=[row["stage"] for row in stages if row["status"] == "needs_changes"],
        recorded_motion_issues=motion.get("issues", []), human_visual_acceptance=False)


def repair_earwear(name, root, source_projects, characters, production, result, provenance, timeout,
                   character_options=None):
    """Create a new typed agent decision against the actual new base candidate."""
    from autospine_workbench.automation.character_region_mounts import save
    from autospine_workbench.automation.production_coverage import inspect as coverage
    if name != "paqiuli":
        return result, None
    scope = coverage(production, result["run_id"])
    unresolved = {row["layer_id"] for row in scope["layers"] if row["unresolved"]}
    if "layer-005" not in unresolved:
        return result, None
    project = provenance["project_id"]
    original_path = source_projects.state_root / f"jobs/character-web-v1/region-mount-decisions/{project}/000000.json"
    original = read_json(original_path, source_projects.state_root)
    original_info = fingerprint(original_path, source_projects.state_root)
    require(canonical_sha256(original) == "36b6d717c00768e25e5438c061ee870ead9a4850dfc5c7cee65b9ecf110931be"
            and original["decision"]["parents"] == {"layer-005": "head"}
            and original["decision"]["decision_source"] == "agent_review"
            and original["authority"] == "none" and original["production_authorized"] is False,
            "earwear_original_semantic_evidence_changed")
    previous_character = result["stages"]["character"]
    files = characters.verified_files(project, previous_character["job_id"])
    context = earwear_context(files, provenance["source_addresses"]["resolved_project_sha256"])
    decision = dict(schema="autospine.region-mount-decision/v1",
                    source_bundle_sha256=previous_character["artifact_sha256"],
                    parents={"layer-005": "head"}, decision_source="agent_review", reversible=True)
    saved = save(characters, project, dict(action="replace", expected_head_sha256=None,
                                         job_id=previous_character["job_id"], decision=decision))
    evidence = dict(scope="new_agent_semantic_judgment_on_byte_matched_original_material",
                    human_acceptance=False, old_bound_decision_transferred=False,
                    original_evidence=original_info, context=context,
                    new_source_bound_decision=saved,
                    initial_run_id=result["run_id"], initial_coverage=scope,
                    initial_null_character_production=result)
    write_report(root / name / "earwear-agent-review.json", evidence)
    info = characters.overview(project)
    require(info["can_build"], "earwear_rebuild_unavailable")
    selected = {key: info[key] for key in (
        "expected_resolved_sha256", "expected_input_sha256", "sleeve_job_id")}
    if character_options is not None:
        selected.update(character_options)
    submitted = characters.submit(project, **selected)
    rebuilt = wait_task(lambda: characters.get(project, submitted["job_id"]),
                        lambda x: x["status"] not in ("pending", "running"), timeout,
                        label=name + ":earwear-character", progress_path=root / name / "earwear-character-progress.json")
    require(rebuilt["status"] == "needs_review", "earwear_character_rebuild_failed")
    evidence["new_character"] = rebuilt
    for _ in range(60):
        if not production.is_active(result["run_id"]):
            break
        time.sleep(.1)
    require(not production.is_active(result["run_id"]), "earwear_revision_wait_for_current_run")
    revised = production.revise(result["run_id"], result["revision"])
    evidence["revised_run_id"] = revised["run_id"]
    write_report(root / name / "earwear-agent-review.json", evidence)
    final = wait_task(lambda: production.get(revised["run_id"]),
                      lambda x: x["status"] not in ("pending", "running"), timeout,
                      label=name + ":revised-production", progress_path=root / name / "revised-production-progress.json")
    require(final["status"] == "needs_review" and final["request"]["character_job_id"] == rebuilt["job_id"],
            "earwear_revised_production_failed")
    require(all(final["stages"][stage]["status"] == "succeeded" for stage in ("character", "body", "joint")),
            "earwear_revised_stages_incomplete")
    require(fingerprint(original_path, source_projects.state_root) == original_info, "earwear_original_evidence_changed")
    evidence["final_run_id"] = final["run_id"]
    evidence["final_coverage"] = coverage(production, final["run_id"])
    write_report(root / name / "earwear-agent-review.json", evidence)
    return final, evidence


def export_candidate(motions, result, path):
    from autospine_workbench.automation.motion_stage_review import inspect as stage_review
    from autospine_workbench.automation.motion_target_jobs import download
    jid = result["stages"]["joint"]["job_id"]
    review = stage_review(motions, jid)
    require(review["revision"] == 0 and review["current"] is None, "new_stage_acceptance_found")
    raw = download(motions, jid)
    with path.open("xb") as handle:
        handle.write(raw)
    with ZipFile(BytesIO(raw)) as bundle:
        names = bundle.namelist()
        require(len(names) == len(set(names)) and "skeleton.json" in names, "export_archive_invalid")
        files = {key: sha256(bundle.read(key)).hexdigest() for key in names}
    require(canonical_sha256(files) == result["stages"]["joint"]["artifact_sha256"], "export_identity_mismatch")
    return review, dict(path=str(path), bytes=len(raw), sha256=sha256(raw).hexdigest(), files=len(files),
                       artifact_sha256=canonical_sha256(files), identity_verified=True)


def resume_skirt(name, root, source_projects, plan, provenance, previous, timeout):
    """Only continue this fixture's own completed technical run, preserving it."""
    from autospine_workbench.project_store import ProjectStore
    from autospine_workbench.automation.character_jobs import CharacterJobs
    from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
    from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
    from autospine_workbench.automation.production_driver import ProductionDriver
    from autospine_workbench.automation.production_jobs import ProductionJobs
    from autospine_workbench.automation.production_coverage import inspect as coverage
    from autospine_workbench.automation.character_region_mounts import overview as mounts, save
    from autospine_workbench.automation.motion_stage_review import inspect as stage_review

    target = root / name / "report.json"
    snapshot = root / name / "first-pass-report.json"
    require(not snapshot.exists(), "owned_run_already_resumed")
    previous_bytes = target.read_bytes()
    with snapshot.open("xb") as handle:
        handle.write(previous_bytes)
    workspace, state = root / name / "workspace", root / name / "state"
    real_path(workspace, root, file=False)
    real_path(state, root, file=False)
    require(previous["workspace"] == str(workspace) and previous["state_root"] == str(state)
            and previous["ok"] and previous["production"]["status"] == "needs_review"
            and previous["stage_review"]["revision"] == 0 and previous["stage_review"]["current"] is None,
            "owned_completed_run_identity_invalid")
    for row in plan.rows():
        require(fingerprint(state / row["target"], state) == {key: row[key] for key in ("bytes", "sha256")},
                "owned_author_closure_changed")
    old_archive = fingerprint(Path(previous["export"]["path"]), root, maximum=256 << 20)
    require(old_archive["sha256"] == previous["export"]["sha256"], "owned_original_export_changed")
    report = dict(previous, ok=False, initial_pass_report=str(snapshot),
                  initial_export=dict(previous["export"]), initial_production=previous["production"],
                  initial_coverage=previous["coverage"], new_agent_strategy_selection=True)
    projects = ProjectStore(workspace, state_root=state, measure_composite_quality=False)
    sleeves = SleeveWebJobs(projects)
    characters = CharacterJobs(projects, sleeves)
    motions = MotionIntakeJobs(projects)
    motions.character_manager = lambda: characters
    production = ProductionJobs(state / "jobs/production-v1", ProductionDriver(motions))
    started = time.monotonic()
    project = provenance["project_id"]
    try:
        original_run = production.get(previous["run_id"])
        require(original_run == previous["production"], "owned_production_journal_changed")
        review = stage_review(motions, original_run["stages"]["joint"]["job_id"])
        require(review["revision"] == 0 and review["current"] is None, "owned_stage_review_changed")
        job = original_run["stages"]["character"]["job_id"]
        files = characters.verified_files(project, job)
        context = skirt_context(files, name, provenance["source_addresses"]["resolved_project_sha256"])
        strategy = dict(scope="new_agent_strategy_on_byte_matched_original_material", context=context,
                        default_production_gap=dict(module="automation/production_preparation.py",
                            reason="skirt_profile_not_in_frozen_request_or_character_launch",
                            initial_null_character_run_complete=True), human_acceptance=False)
        current = mounts(characters, project)
        if current["active"]:
            expected = previous.get("new_agent_adjustment", {}).get("new_source_bound_decision", {})
            require(name == "paqiuli" and current["head_sha256"] == expected.get("head_sha256")
                    and current["review"]["decision"]["decision_source"] == "agent_review"
                    and current["review"]["decision"]["parents"] == {"layer-005": "head"},
                    "owned_mount_not_fixture_agent_decision")
            strategy["prior_agent_mount_revoked_for_new_skirt_base"] = save(characters, project,
                dict(action="revoke", expected_head_sha256=current["head_sha256"]))
        info = characters.overview(project)
        require(info["can_build"], "skirt_rebuild_unavailable")
        options = {key: info[key] for key in ("expected_resolved_sha256", "expected_input_sha256", "sleeve_job_id")}
        options["skirt_profile"] = "reviewed-torso-waist-v2"
        submitted = characters.submit(project, **options)
        base = wait_task(lambda: characters.get(project, submitted["job_id"]),
                         lambda value: value["status"] not in ("pending", "running"), timeout,
                         label=name + ":skirt-character", progress_path=root / name / "skirt-character-progress.json")
        require(base["status"] == "needs_review", "skirt_character_rebuild_failed")
        if name == "paqiuli":
            new_files = characters.verified_files(project, base["job_id"])
            ear = earwear_context(new_files, context["resolved_project_sha256"])
            current = mounts(characters, project)
            strategy["earwear_context"] = ear
            strategy["new_source_bound_earwear"] = save(characters, project,
                dict(action="replace", expected_head_sha256=current["head_sha256"], job_id=base["job_id"],
                     decision=dict(schema="autospine.region-mount-decision/v1", source_bundle_sha256=base["artifact_sha256"],
                                   parents={"layer-005": "head"}, decision_source="agent_review", reversible=True)))
            submitted = characters.submit(project, **options)
            base = wait_task(lambda: characters.get(project, submitted["job_id"]),
                             lambda value: value["status"] not in ("pending", "running"), timeout,
                             label=name + ":skirt-earwear-character", progress_path=root / name / "skirt-earwear-progress.json")
            require(base["status"] == "needs_review", "skirt_earwear_character_failed")
        strategy["new_character"] = base
        report["new_skirt_strategy"] = strategy
        write_report(target, report)
        revised = production.revise(previous["run_id"], original_run["revision"])
        result = wait_task(lambda: production.get(revised["run_id"]),
                           lambda value: value["status"] not in ("pending", "running"), timeout,
                           label=name + ":skirt-production", progress_path=root / name / "skirt-production-progress.json")
        require(result["status"] == "needs_review" and result["request"]["character_job_id"] == base["job_id"],
                "skirt_revised_production_failed")
        require(all(result["stages"][stage]["status"] == "succeeded" for stage in ("character", "body", "joint")),
                "skirt_revised_stages_incomplete")
        report.update(run_id=result["run_id"], production=result, coverage=coverage(production, result["run_id"]))
        report["stage_review"], report["export"] = export_candidate(motions, result,
            root / name / ("candidate-" + result["stages"]["joint"]["job_id"] + ".zip"))
        require(fingerprint(Path(previous["export"]["path"]), root, maximum=256 << 20) == old_archive,
                "owned_original_export_changed")
        plan.check_unchanged()
        report.update(ok=True, complete_character_coverage=report["coverage"]["unresolved_layer_count"] == 0)
        return report
    except Exception as exc:
        report["resume_error"] = dict(type=type(exc).__name__, reason=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        for manager in (production, motions, characters, sleeves):
            manager.close()
        report["resume_elapsed_seconds"] = time.monotonic() - started
        write_report(target, report)


def run_case(name, root, source_projects, plan, provenance, fbx, timeout, skirt_profile=None):
    from autospine_workbench.project_store import ProjectStore
    from autospine_workbench.automation.psd_import_jobs import PsdImportJobs
    from autospine_workbench.automation.character_jobs import CharacterJobs
    from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs
    from autospine_workbench.automation.motion_intake_jobs import MotionIntakeJobs
    from autospine_workbench.automation.production_driver import ProductionDriver
    from autospine_workbench.automation.production_jobs import ProductionJobs
    from autospine_workbench.automation.production_coverage import inspect as coverage
    from autospine_workbench.automation.motion_stage_review import inspect as stage_review
    from autospine_workbench.automation.motion_target_jobs import download

    case = CASES[name]
    workspace, state = root / name / "workspace", root / name / "state"
    workspace.mkdir(parents=True)
    state.mkdir()
    projects = ProjectStore(workspace, state_root=state, measure_composite_quality=False)
    imports = PsdImportJobs(projects)
    sleeves, characters, motions, production = None, None, None, None
    report = dict(name=name, scope="existing-author-input-replay", author_provenance=provenance,
                  workspace=str(workspace), state_root=str(state), ok=False,
                  new_human_review=False, new_visual_acceptance=False, old_stage_review_transferred=False)
    target = root / name / "report.json"
    started = time.monotonic()
    psd = source_projects.workspace_root / (name + ".psd")
    psd_before = fingerprint(psd, source_projects.workspace_root)
    audit_path = source_projects.audit_root / provenance["project_id"] / "audit.json"
    audit_before = fingerprint(audit_path, source_projects.audit_root)
    write_report(target, report)
    try:
        require(fingerprint(psd, source_projects.workspace_root)["sha256"] == case["psd_sha256"], "source_psd_changed")
        with psd.open("rb") as stream:
            job = imports.upload(stream, psd.stat().st_size, psd.name)
        imported = wait_task(lambda: imports.get(job["job_id"]),
                             lambda x: x["status"] not in ("pending", "running"), 240, label=name + ":psd",
                             progress_path=root / name / "psd-progress.json")
        report["psd_import"] = imported
        require(imported["status"] == "succeeded" and imported["project_id"] == provenance["project_id"],
                "new_psd_import_failed")
        project = imported["project_id"]
        require(canonical_sha256(projects._record(project).audit) ==
                canonical_sha256(source_projects._record(project).audit), "new_psd_audit_not_identical")
        # PSD import creates only the new intake job and asset metadata. It is
        # intentionally excluded from the author-input destination guard.
        author_state = root / name / "author-staging"
        author_state.mkdir()
        copy_author_closure(plan, author_state)
        for item in plan.rows():
            source, destination = author_state / item["target"], state / item["target"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            require(not destination.exists(), "author_restore_would_overwrite")
            os.rename(source, destination)
        restored, restored_provenance = build_author_plan(projects, name)
        require(restored_provenance["source_addresses"] == provenance["source_addresses"], "author_restore_identity_changed")
        require([(x["target"], x["sha256"]) for x in restored.rows()] ==
                [(x["target"], x["sha256"]) for x in plan.rows()], "author_restore_inventory_changed")
        report["author_restore"] = dict(byte_identical=True, files=len(plan.files),
                                        closure_sha256=provenance["closure_sha256"], production_reader_verified=True)
        write_report(target, report)
        sleeves = SleeveWebJobs(projects)
        characters = CharacterJobs(projects, sleeves)
        motions = MotionIntakeJobs(projects)
        motions.character_manager = lambda: characters
        with fbx.open("rb") as stream:
            upload = motions.upload(stream, fbx.stat().st_size, "breathing_idle.fbx", "front")
        source = wait_task(lambda: motions.get(upload["job_id"]),
                          lambda x: x["status"] not in ("pending", "running"), 300, label=name + ":fbx",
                          progress_path=root / name / "fbx-progress.json")
        report["fbx_import"] = source
        require(source["status"] == "succeeded" and source["source_sha256"] == SOURCE_FBX_SHA
                and source["result"]["motion_status"] == "compiled"
                and source["result"]["fbx_bridge"]["passed"], "new_fbx_conversion_failed")
        require(source["result"]["frame_count"] == 299, "full_source_clip_required")
        body, joint = production_settings()
        production = ProductionJobs(state / "jobs/production-v1", ProductionDriver(motions))
        request = production_request(project, source["job_id"], body, joint, skirt_profile)
        report["selected_character_options"] = request.get("character_options")
        submitted = production.submit(request)
        report["run_id"] = submitted["run_id"]
        write_report(target, report)
        result = wait_task(lambda: production.get(submitted["run_id"]),
                          lambda x: x["status"] not in ("pending", "running"), timeout, label=name + ":production",
                          progress_path=root / name / "production-progress.json")
        report["production"] = result
        require(result["status"] == "needs_review", "production_not_needs_review:" + str(result.get("reason_code")))
        require(result["request"]["character_job_id"] is None, "existing_character_reused")
        require(all(result["stages"][stage]["status"] == "succeeded" for stage in ("source", "bindings", "character", "body", "joint")),
                "continuous_stages_incomplete")
        if case["route"] == "sleeves":
            require(result["stages"]["sleeves"]["status"] == "succeeded", "full_sleeve_stage_missing")
        initial_files = (characters.verified_files(project, result["stages"]["character"]["job_id"])
                         if name == "paqiuli" and skirt_profile is not None else None)
        result, adjustment = repair_earwear(name, root, source_projects, characters, production, result,
                                           provenance, timeout, request.get("character_options"))
        if adjustment:
            report["new_agent_adjustment"] = adjustment
            report["production"] = result
            report["run_id"] = result["run_id"]
        report["coverage"] = coverage(production, result["run_id"])
        jid = result["stages"]["joint"]["job_id"]
        review = stage_review(motions, jid)
        require(review["revision"] == 0 and review["current"] is None, "new_stage_acceptance_found")
        report["stage_review"] = review
        raw = download(motions, jid)
        archive = root / name / "candidate.zip"
        with archive.open("xb") as handle:
            handle.write(raw)
        with ZipFile(BytesIO(raw)) as bundle:
            names = bundle.namelist()
            require(len(names) == len(set(names)) and "skeleton.json" in names, "export_archive_invalid")
            files = {key: sha256(bundle.read(key)).hexdigest() for key in names}
        require(canonical_sha256(files) == result["stages"]["joint"]["artifact_sha256"], "export_identity_mismatch")
        report["export"] = dict(path=str(archive), bytes=len(raw), sha256=sha256(raw).hexdigest(),
                                files=len(files), artifact_sha256=canonical_sha256(files), identity_verified=True)
        report["technical_statistics"] = technical_statistics(review, archive)
        if skirt_profile is not None:
            if name == "paqiuli":
                original, original_info = original_residual_files(source_projects)
                final_files = characters.verified_files(project, result["stages"]["character"]["job_id"])
                retained = residual_retention_evidence(original, initial_files, final_files,
                    provenance["source_addresses"], report["coverage"])
                retained["original_evidence"] = original_info
                report["residual_retention_evidence"] = retained
            else:
                require(report["coverage"]["unresolved_layer_count"] == 0
                        and not any(layer["missing_region_ids"] for layer in report["coverage"]["layers"]),
                        "ordinary_character_coverage_incomplete")
        report["ok"] = True
        report["complete_character_coverage"] = report["coverage"]["unresolved_layer_count"] == 0
        return report
    except Exception as exc:
        report["error"] = dict(type=type(exc).__name__, reason=str(exc), traceback=traceback.format_exc())
        raise
    finally:
        for manager in (production, motions, characters, sleeves, imports):
            if manager is not None:
                manager.close()
        report["elapsed_seconds"] = time.monotonic() - started
        report["source_input_unchanged"] = False
        try:
            plan.check_unchanged()
            require(fingerprint(psd, source_projects.workspace_root) == psd_before, "source_psd_changed")
            require(fingerprint(audit_path, source_projects.audit_root) == audit_before, "source_audit_changed")
            require(fingerprint(fbx, source_projects.state_root)["sha256"] == SOURCE_FBX_SHA, "source_fbx_changed")
            report["source_input_unchanged"] = True
        except Exception as exc:
            report["source_integrity_error"] = str(exc)
            report["ok"] = False
        write_report(target, report)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--engine-root", required=True, type=Path)
    parser.add_argument("--engine-manifest-sha256", required=True,
                        help="Exact allowlisted frozen engine-distribution.json digest; never accepts unknown versions.")
    parser.add_argument("--source-workspace", required=True, type=Path)
    parser.add_argument("--source-state", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--blender", required=True, type=Path)
    parser.add_argument("--capture-bundle", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--character-skirt-profile", choices=("reviewed-torso-waist-v2",),
                        help="Explicit typed recipe for the first null-character production; omission preserves legacy defaults.")
    parser.add_argument("--resume-owned-run", action="store_true",
                        help="Continue only this fixture's completed isolated run using new typed skirt strategies.")
    parser.add_argument("--case", choices=("both", *CASES), default="both")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()
    from autospine_workbench.project_store import ProjectStore
    workspace, state = args.source_workspace.absolute(), args.source_state.absolute()
    real_path(workspace, workspace, file=False)
    real_path(state, state, file=False)
    projects = ProjectStore(workspace, state_root=state, measure_composite_quality=False)
    previous_report = None
    if args.resume_owned_run:
        root = real_path(args.output.absolute(), args.output.absolute(), file=False)
        require(not root.is_relative_to(state) and not root.is_relative_to(projects.audit_root), "output_overlaps_source")
        previous_report = read_json(root / "report.json", root)
        require(not args.plan_only, "owned_run_resume_not_plan_only")
        require_completed_owned_report(previous_report)
        require(not (root / "first-pass-report.json").exists(), "owned_run_already_resumed")
        with (root / "first-pass-report.json").open("xb") as handle:
            handle.write((root / "report.json").read_bytes())
    else:
        root = reserve_output(args.output, state, projects.audit_root)
    names = list(CASES) if args.case == "both" else [args.case]
    report = dict(schema="autospine.studio-continuous-production-test/v1", ok=False,
                  scope="existing-author-input-replay", new_material_validation=False,
                  human_visual_acceptance=False, source_state_written=False,
                  ordinary_and_sleeve_s1_s6_human_walkthrough="not_performed", cases={}, errors=[])
    report["selected_character_options"] = (dict(skirt_profile=args.character_skirt_profile)
                                             if args.character_skirt_profile else None)
    try:
        require(60 <= args.timeout <= 7200, "timeout_invalid")
        require(args.engine_root.is_absolute(), "engine_root_absolute_required")
        require(args.engine_manifest_sha256 in FROZEN_RELEASES, "engine_manifest_pin_not_allowlisted")
        engine_before = engine_source_snapshot(args.engine_manifest_sha256)
        report["engine_identity"] = engine_before
        if previous_report:
            require(previous_report["engine_identity"] == engine_before, "owned_engine_identity_changed")
            report["first_pass_report"] = str(root / "first-pass-report.json")
        plans = {}
        source_snapshots = {}
        for name in names:
            plan, provenance = build_author_plan(projects, name)
            psd = workspace / (name + ".psd")
            require(fingerprint(psd, workspace)["sha256"] == CASES[name]["psd_sha256"], "source_psd_changed")
            audit_path = projects.audit_root / provenance["project_id"] / "audit.json"
            for source_path, source_root in ((psd, workspace), (audit_path, projects.audit_root)):
                source_snapshots[str(source_path)] = dict(root=str(source_root), **fingerprint(source_path, source_root))
            plans[name] = plan, provenance
            report["cases"][name] = dict(plan=plan.rows(), provenance=provenance, psd=str(psd))
            if previous_report:
                original = previous_report["cases"][name]
                require(original["plan"] == plan.rows() and original["provenance"] == provenance,
                        "owned_source_closure_changed")
        fbx = state / "jobs/motion-intake-v1" / SOURCE_FBX / "source.fbx"
        require(fingerprint(fbx, state)["sha256"] == SOURCE_FBX_SHA, "source_fbx_changed")
        report["source_fbx"] = dict(path=str(fbx), **fingerprint(fbx, state))
        source_snapshots[str(fbx)] = dict(root=str(state), **fingerprint(fbx, state))
        report["source_snapshots"] = source_snapshots
        write_report(root / ("resume-plan.json" if previous_report else "plan.json"), report)
        if args.plan_only:
            report.update(ok=True, status="planned_not_executed")
            return 0
        blender, capture = args.blender.absolute(), args.capture_bundle.absolute()
        real_path(blender, blender.parent, maximum=256 << 20)
        real_path(capture, capture, file=False)
        capture_before = capture_snapshot(capture)
        blender_before = blender_snapshot(blender.parent.parent)
        report["runtime_environment"] = dict(capture_manifest_sha256=CAPTURE_MANIFEST_SHA,
                                              blender_manifest_sha256=BLENDER_MANIFEST_SHA,
                                              interpreter=sys.executable, engine_source=str(ENGINE))
        write_report(root / "report.json", report)
        with runtime_environment(blender, capture):
            for name in names:
                plan, provenance = plans[name]
                if previous_report:
                    report["cases"][name]["result"] = resume_skirt(name, root, projects, plan, provenance,
                        previous_report["cases"][name]["result"], args.timeout)
                else:
                    report["cases"][name]["result"] = run_case(name, root, projects, plan, provenance,
                        fbx, args.timeout, args.character_skirt_profile)
        require(capture_snapshot(capture) == capture_before, "capture_bundle_changed")
        require(blender_snapshot(blender.parent.parent) == blender_before, "blender_bundle_changed")
        require(engine_source_snapshot(args.engine_manifest_sha256) == engine_before, "engine_source_changed")
        for source_path, info in source_snapshots.items():
            require(fingerprint(Path(source_path), Path(info["root"])) ==
                    {key: info[key] for key in ("bytes", "sha256")}, "original_source_changed")
        for plan, _ in plans.values():
            plan.check_unchanged()
        report.update(ok=True, status="new_candidates_exported_needs_review", capture_inventory_unchanged=True,
                      blender_inventory_unchanged=True, frozen_engine_source_unchanged=True,
                      original_source_snapshots_unchanged=True)
        return 0
    except Exception as exc:
        report["errors"].append(dict(type=type(exc).__name__, reason=str(exc), traceback=traceback.format_exc()))
        return 1
    finally:
        write_report(root / "report.json", report)
        print(json.dumps(dict(output=str(root), ok=report["ok"], status=report.get("status"), errors=report["errors"])), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
