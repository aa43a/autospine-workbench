"""Replayable bilateral component hypotheses with exact retained residual pixels."""

import base64
from copy import deepcopy
import hashlib

from ..asset.joints.partition_mesh import build_region
from ..asset.joints.partition_pixels import partition
from ..asset.joints.structure_candidates import build_structure_candidates


def build_partitions(inputs):
    draft = deepcopy(inputs.draft)
    for record, binding in zip(draft["records"], inputs.bindings["bindings"]):
        option = next((o for o in binding["options"] if o["id"] == record["option_id"]), None)
        if record["action"] == "bind" and option and len(option["bone_ids"]) == 6:
            record.update(action="pending", option_id=None)
    structure = build_structure_candidates(inputs.candidate, inputs.assisted, inputs.skeleton,
                                           inputs.bindings, draft, inputs.images)
    sources = {r["layer_id"]: r for r in inputs.candidate["layers"]}
    result = []
    for proposal in structure["layers"]:
        if not proposal["proposal"] or proposal["proposal"]["kind"] != "component_partition":
            continue
        source = sources[proposal["layer_id"]]
        files, qa = partition(inputs.images[source["layer_id"]], source, proposal)
        layers, meshes, images = [], [], {}
        for side, filename in (("l", "left.png"), ("r", "right.png")):
            chain = next(c["bone_ids"] for c in proposal["components"] if c["side"] == side)
            mesh = build_region(files[filename], source, side, chain, inputs.skeleton)
            derived = deepcopy(source)
            derived.update(layer_id=mesh["layer_id"], image_sha256=mesh["image_sha256"],
                           source_layer_id=source["layer_id"])
            layers.append(derived)
            meshes.append(mesh)
            images[mesh["layer_id"]] = base64.b64encode(files[filename]).decode("ascii")
        # A topology failure keeps the original source as context. No partial disappearance.
        if any(not mesh["weights"] for mesh in meshes):
            continue
        residual = deepcopy(source)
        residual.update(layer_id=source["layer_id"] + "-residual", source_layer_id=source["layer_id"],
                        image_sha256=hashlib.sha256(files["residual.png"]).hexdigest(),
                        empty=qa["visible_pixel_counts"]["3"] == 0)
        layers.append(residual)
        images[residual["layer_id"]] = base64.b64encode(files["residual.png"]).decode("ascii")
        result.append({"source_layer_id": source["layer_id"], "layers": layers, "meshes": meshes,
                       "images_base64": images, "qa": qa, "authority": "none",
                       "reason_code": "partition_assignment_review_required"})
    return result


def expand_inputs(inputs, partitions):
    from types import SimpleNamespace
    source = deepcopy(inputs.candidate)
    images = dict(inputs.images)
    replacements = {p["source_layer_id"]: p for p in partitions}
    source["layers"] = [layer for original in source["layers"] for layer in
                        replacements.get(original["layer_id"], {"layers": [original]})["layers"]]
    for part in partitions:
        for name, encoded in part["images_base64"].items():
            images[name] = base64.b64decode(encoded, validate=True)
    return SimpleNamespace(candidate=source, skeleton=inputs.skeleton,
                           source_addresses=inputs.source_addresses, images=images)
