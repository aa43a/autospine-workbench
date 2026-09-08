"""Dataset intake, split freezing and honest metrics without hand-entered SHAs."""

import argparse
import json
from pathlib import Path
import re

from ..resolved_project import canonical_sha256
from .artifacts import export_document, publish_report, read_input
from .manifest import import_inventory, freeze_split
from .metrics import build_metrics
from .source_files import verify_sources
from .split_proposal import propose_split
from .store import BenchmarkManifestStore
from .validation import validate_benchmark_manifest


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    repository = Path(__file__).resolve().parents[3]
    result.add_argument("--state-root", type=Path, default=repository / "workspace")
    sub = result.add_subparsers(dest="command", required=True)
    intake = sub.add_parser("intake")
    intake.add_argument("--inventory", required=True, type=Path)
    intake.add_argument("--dataset-id", default="touhou-20-v1")
    intake.add_argument("--workspace", required=True, type=Path)
    for name in ("verify-sources", "propose-split", "freeze-split", "observations-template", "metrics", "lint-inputs"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--manifest", required=True, type=Path)
        if name in {"verify-sources", "lint-inputs"}:
            cmd.add_argument("--workspace", required=True, type=Path)
            if name == "lint-inputs":
                cmd.add_argument("--split", default="development", choices=("development", "visible", "holdout", "reserve"))
        elif name == "propose-split":
            cmd.add_argument("--development-source", action="append", default=[])
        elif name == "freeze-split":
            cmd.add_argument("--proposal", required=True, type=Path)
        elif name == "observations-template":
            cmd.add_argument("--code-commit", required=True)
            cmd.add_argument("--profile", default="production_review")
            cmd.add_argument("--target-version", default="4.3.26")
        elif name == "metrics":
            cmd.add_argument("--observations", required=True, type=Path)
        cmd.add_argument("--output", type=Path)
    intake.add_argument("--output", type=Path)
    from .mapping_cli import register_parser

    register_parser(sub)
    from .mapping_decision_cli import register_parsers

    register_parsers(sub)
    from .semantic_cli import register_parser as register_semantic_parser

    register_semantic_parser(sub)
    from .annotation_cli import register_parsers as register_annotation_parsers

    register_annotation_parsers(sub)
    from .joint_comparison_cli import register_parser as register_comparison_parser

    register_comparison_parser(sub)
    from .contact_probe_cli import register_parser as register_contact_parser

    register_contact_parser(sub)
    from .contact_screen_cli import register_parser as register_screen_parser

    register_screen_parser(sub)
    from .pose_contact_cli import register_parser as register_pose_parser

    register_pose_parser(sub)
    from .r2a_cli import register_parser as register_r2a_parser

    register_r2a_parser(sub)
    from .joint_reference_cli import register_parser as register_reference_parser
    from .pose_accuracy_cli import register_parser as register_accuracy_parser
    register_reference_parser(sub)
    register_accuracy_parser(sub)
    from .assisted_skeleton_cli import register_parser as register_assisted_skeleton_parser
    register_assisted_skeleton_parser(sub)
    from .region_binding_cli import register_parser as register_binding_parser
    register_binding_parser(sub)
    from .layer_binding_cli import register_parser as register_layer_binding_parser
    register_layer_binding_parser(sub)
    from .chain_coverage_cli import register_parser as register_coverage_parser
    register_coverage_parser(sub)
    from .mesh_candidate_cli import register_parser as register_mesh_parser
    register_mesh_parser(sub)
    from .mesh_refinement_cli import register_parser as register_refinement_parser
    register_refinement_parser(sub)
    from .mesh_area_cli import register_parser as register_area_parser
    register_area_parser(sub)
    from .elbow_comparison_cli import register_parser as register_elbow_parser
    register_elbow_parser(sub)
    from .elbow_constraint_cli import register_parser as register_constraint_parser
    register_constraint_parser(sub)
    from .elbow_bake_cli import register_parser as register_bake_parser
    register_bake_parser(sub)
    from .elbow_target_cli import register_parser as register_target_parser
    register_target_parser(sub)
    return result


def _execute(args):
    if args.command == 'export-elbow-spine43':
        from .elbow_target_cli import execute
        return execute(args)
    if args.command == 'bake-elbow-preview':
        from .elbow_bake_cli import execute
        return execute(args)
    if args.command == 'correct-elbow-preview':
        from .elbow_constraint_cli import execute
        return execute(args)
    if args.command == 'compare-elbow-deformation':
        from .elbow_comparison_cli import execute
        return execute(args)
    if args.command == 'screen-mesh-area':
        from .mesh_area_cli import execute
        return execute(args)
    if args.command == 'refine-mesh-weights':
        from .mesh_refinement_cli import execute
        return execute(args)
    if args.command == 'build-weighted-mesh':
        from .mesh_candidate_cli import execute
        return execute(args)
    if args.command == 'analyze-chain-coverage':
        from .chain_coverage_cli import execute
        return execute(args)
    if args.command == 'build-layer-bindings':
        from .layer_binding_cli import execute
        return execute(args)
    if args.command == 'build-region-bindings':
        from .region_binding_cli import execute
        return execute(args)
    if args.command == 'build-assisted-skeleton':
        from .assisted_skeleton_cli import execute
        return execute(args)
    if args.command in ('record-joint-reference', 'evaluate-pose-benchmark'):
        if args.command == 'record-joint-reference':
            from .joint_reference_cli import execute
        else:
            from .pose_accuracy_cli import execute
        return execute(args)
    if args.command == "build-r2a":
        from .r2a_cli import execute

        return execute(args)
    if args.command == "match-pose-contacts":
        from .pose_contact_cli import execute

        return execute(args)
    if args.command == "screen-contacts":
        from .contact_screen_cli import execute

        return execute(args)
    if args.command == "probe-contacts":
        from .contact_probe_cli import execute

        return execute(args)
    if args.command == "compare-joints":
        from .joint_comparison_cli import execute

        return execute(args)
    if args.command in {"joint-review", "record-semantic-review"}:
        from .annotation_cli import execute

        return execute(args)
    if args.command == "semantic-review":
        from .semantic_cli import execute

        return execute(args)
    if args.command in {"record-mapping-review", "annotation-template"}:
        from .mapping_decision_cli import execute

        return execute(args)
    if args.command == "mapping-review":
        from .mapping_cli import execute

        return execute(args)
    if args.command == "intake":
        manifest = import_inventory(read_input(args.inventory), dataset_id=args.dataset_id)
        checked = verify_sources(manifest, args.workspace)
        if checked["status"] != "verified":
            return checked, "source-verifications", manifest["dataset_id"], 2
        return manifest, "manifests", manifest["dataset_id"], 0
    manifest = read_input(args.manifest)
    validate_benchmark_manifest(manifest)
    name = manifest["dataset_id"]
    if args.command == "verify-sources":
        checked = verify_sources(manifest, args.workspace)
        return checked, "source-verifications", name, 0 if checked["status"] == "verified" else 2
    if args.command == "lint-inputs":
        from .input_batch import lint_inputs

        report = lint_inputs(manifest, args.workspace, split=args.split)
        passed = all(row["status"] == "analyzed" and row["analysis"]["quality"] != "blocked"
                     for row in report["records"])
        return report, "input-quality", name, 0 if passed else 2
    if args.command == "propose-split":
        return propose_split(manifest, development_sources=args.development_source), "split-proposals", name, 0
    if args.command == "freeze-split":
        proposal = read_input(args.proposal)
        if proposal.get("schema") != "autospine.benchmark-split-proposal/v1" \
                or proposal.get("authority") != "none" \
                or proposal.get("dataset_sha256") != canonical_sha256(manifest):
            raise ValueError("benchmark_split_source_mismatch")
        return freeze_split(manifest, proposal["assignment"]), "manifests", name, 0
    if args.command == "observations-template":
        value = {"schema": "autospine.benchmark-observations/v1", "authority": "none",
                 "dataset_sha256": canonical_sha256(manifest), "code_commit": args.code_commit,
                 "profile": args.profile, "target_version": args.target_version, "records": []}
        build_metrics(manifest, value)
        return value, "observations", name, 0
    return build_metrics(manifest, read_input(args.observations)), "metrics", name, 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        document, kind, dataset_id, code = _execute(args)
        if kind == 'weighted-mesh-candidates':
            from .mesh_storage import publish_mesh_report,export_mesh
            digest = publish_mesh_report(args.state_root,dataset_id,document)
        else:
            digest = BenchmarkManifestStore(args.state_root).publish(document) if kind == "manifests" \
                else publish_report(args.state_root, dataset_id, kind, document)
        if args.output is not None:
            if kind == 'weighted-mesh-candidates':
                export_mesh(args.output,document)
            else:
                export_document(args.output, document)
            print(json.dumps({"status": "written", "artifact_sha256": digest,
                              "authority": "none", "kind": kind}, sort_keys=True))
        else:
            print(json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return code
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        reason = getattr(exc, "reason_code", str(exc))
        if type(reason) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", reason):
            reason = "benchmark_request_failed"
        print(json.dumps({"status": "blocked", "reason_code": reason, "authority": "none"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
