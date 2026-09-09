"""Weighted preview adapter using existing local-coordinate and FK conventions."""

from copy import deepcopy
import math

from ...resolved_project import canonical_sha256
from .continuous_pose import inspect, world


def _local(point, bone):
    x, y = (point[i] - bone["head_xy"][i] for i in (0, 1))
    angle = math.radians(-bone["world_rotation_degrees"])
    return [x * math.cos(angle) - y * math.sin(angle),
            x * math.sin(angle) + y * math.cos(angle)]


def rigid_quad(source, bone):
    x, y, right, bottom = source["bbox"]
    points = [[x, y], [right, y], [right, bottom], [x, bottom]]
    return {"layer_id": source["layer_id"], "vertices_xy": points,
            "triangles": [[0, 1, 2], [0, 2, 3]],
            "uvs": [[0, 0], [1, 0], [1, 1], [0, 1]],
            "weights": [[{"bone_id": bone["id"], "local_xy": _local(p, bone),
                          "weight": 1.0}] for p in points]}


def build_document(candidate, skeleton, meshes, motion, rigid_bones=None):
    """Unbound source layers remain explicit rigid context, with unchanged RGBA."""
    rigid_bones = rigid_bones or {}
    bone_map = {b["id"]: b for b in skeleton["bones"]}
    indices = {name: index for index, name in enumerate(bone_map)}
    bones = []
    for bone in skeleton["bones"]:
        local = bone["setup_local"]
        row = {"name": bone["id"], "x": local["x"], "y": -local["y"],
               "rotation": -local["rotation_degrees"], "length": bone["length"]}
        if bone["parent_id"] is not None:
            row["parent"] = bone["parent_id"]
        bones.append(row)
    slots, attachments, regions, context = [], {}, [], []
    for source in candidate["layers"]:
        name = source["layer_id"]
        x, y, right, bottom = source["bbox"]
        if source.get("empty") or not source.get("visible", True) or right <= x or bottom <= y:
            continue
        mesh = meshes.get(name)
        if mesh is None:
            bone = bone_map[rigid_bones.get(name, "root")]
            mesh = rigid_quad(source, bone)
            context.append(name)
        encoded = []
        for influences in mesh["weights"]:
            if abs(sum(w["weight"] for w in influences) - 1) > 1e-7:
                raise ValueError("animated_weights_invalid")
            encoded.append(len(influences))
            for influence in influences:
                lx, ly = influence["local_xy"]
                encoded.extend([indices[influence["bone_id"]], lx, -ly, influence["weight"]])
        slots.append({"name": name, "bone": mesh["weights"][0][0]["bone_id"], "attachment": name})
        attachments[name] = {name: {
            "type": "mesh", "path": name, "vertices": encoded,
            "uvs": [value for point in mesh["uvs"] for value in point],
            "triangles": [value for triangle in mesh["triangles"] for value in triangle],
            "width": right - x, "height": bottom - y,
        }}
        regions.append({"id": name, "setup_vertices_xy": deepcopy(mesh["vertices_xy"]),
                        "source_mesh_status": "candidate" if name in meshes else "rigid_context",
                        "review_status": "needs_review"})
    tracks = {name: {"rotate": [{"time": k["time"], "value": -k["degrees"]}
                                for k in channels["rotation"]]}
              for name, channels in motion["bones"].items()}
    document = {
        "skeleton": {"spine": "4.3.26", "hash": canonical_sha256(motion),
                     "images": "./images/", "x": 0, "y": -candidate["canvas"][1],
                     "width": candidate["canvas"][0], "height": candidate["canvas"][1], "fps": 30},
        "bones": bones, "slots": slots,
        "skins": [{"name": "default", "attachments": attachments}], "constraints": [],
        "animations": {motion["clip"]: {"bones": tracks}},
    }
    setup = world(document, 0)
    error = max((math.dist(actual, [expected[0], -expected[1]])
                 for r in regions for actual, expected in zip(setup[r["id"]], r["setup_vertices_xy"])), default=0)
    if error > 1e-6:
        raise ValueError("animated_setup_reconstruction_failed")
    return document, regions, context, error


def inspect_document(document):
    """Reuse the independent sampler; no claim about continuous or visual seam safety."""
    return inspect(document)
