"""Raw clothing-name pair hypotheses; geometric contact never assigns joints."""
from copy import deepcopy
import hashlib
import json
import re

from ..alpha_geometry import AlphaGeometryLimitError, analyze_alpha_image
from ..contact_geometry import contact_between_alpha
from ..png_rgba import RgbaPngError, decode_rgba_png
from ..resolved_project import canonical_sha256

SCHEMA = "autospine.benchmark-contact-probe/v1"
RELATIONS = (("torso_arm", "topwear", "handwear"),
             ("pelvis_leg", "bottomwear", "legwear"), ("leg_foot", "legwear", "footwear"))
WARNINGS = ("semantic_roles_unreviewed", "character_sides_unreviewed", "joint_assignment_blocked")
MAX_BYTES = 128 * 1024 * 1024
MAX_PIXELS = 32 * 1024 * 1024
MAX_RUNS = 32768
MAX_PAIRS = 64
MAX_OUTPUT_BYTES = 120 * 1024


def _require(condition, code):
    if not condition:
        raise ValueError("benchmark_contact_probe_" + code)


def _prepare(candidate, images):
    _require(type(candidate) is dict and candidate.get("schema") == "autospine.benchmark-semantic-candidates/v1"
             and candidate.get("authority") == "none" and candidate.get("coordinate_system") == "psd_canvas",
             "candidate_invalid")
    layers, canvas = candidate.get("layers"), candidate.get("canvas")
    _require(type(canvas) is list and len(canvas) == 2 and
             all(type(v) is int and 0 < v <= 4096 for v in canvas), "canvas_invalid")
    _require(type(layers) is list and 0 < len(layers) <= 256, "layers_invalid")
    ids = [row.get("layer_id") for row in layers if type(row) is dict]
    _require(len(ids) == len(layers) and all(type(v) is str for v in ids)
             and len(set(ids)) == len(ids), "layers_invalid")
    _require(type(images) is dict and set(images) == set(ids), "images_invalid")
    _require(all(type(v) is bytes for v in images.values())
             and sum(map(len, images.values())) <= MAX_BYTES, "resource_limit")
    result, pixels, runs = [], 0, 0
    for layer in layers:
        raw, image_ref, box = images[layer["layer_id"]], layer.get("image"), layer.get("bbox")
        _require(type(image_ref) is dict and type(image_ref.get("byte_size")) is int
                 and len(raw) == image_ref["byte_size"]
                 and hashlib.sha256(raw).hexdigest() == layer.get("image_sha256") == image_ref.get("sha256"),
                 "image_changed")
        _require(type(box) is list and len(box) == 4 and all(type(v) is int for v in box)
                 and box[0] <= box[2] and box[1] <= box[3], "bbox_invalid")
        image = decode_rgba_png(raw)
        # Audited empty layers are exported as a transparent 1x1 placeholder.
        empty = layer.get("observed", {}).get("empty") is True
        _require(not empty or not any(image.pixels[3::4]), "empty_mask_mismatch")
        _require((image.width, image.height) == (box[2]-box[0], box[3]-box[1])
                 or (empty and image.width == image.height == 1), "image_dimensions_mismatch")
        pixels += image.width * image.height
        _require(pixels <= MAX_PIXELS, "resource_limit")
        name = layer.get("name")
        _require(type(name) is str, "name_invalid")
        normalized = " ".join(name.lower().split())
        base = re.sub(r"-[lr]$", "", normalized)
        outside = box[0] < 0 or box[1] < 0 or box[2] > canvas[0] or box[3] > canvas[1]
        geometry = None
        if not empty and not outside and base in {name for _, a, b in RELATIONS for name in (a, b)}:
            geometry = analyze_alpha_image(image, canvas_offset_xy=(box[0], box[1]), threshold=9,
                                           max_runs=MAX_RUNS)
            runs += geometry.run_count
            _require(runs <= MAX_RUNS, "resource_limit")
            empty = geometry.foreground_area == 0
        result.append((layer["layer_id"], base, empty, outside, geometry))
    return result


def build_contact_probe(candidate, images):
    """Verify immutable raster inputs; all pairings remain semantic hypotheses."""
    try:
        layers = _prepare(candidate, images)
        relations, pair_count = [], 0
        for relation, reference, child in RELATIONS:
            left = [r for r in layers if r[1] == reference]
            right = [r for r in layers if r[1] == child]
            reasons = list(WARNINGS)
            if not left:
                reasons.append("missing_reference_layer")
            if not right:
                reasons.append("missing_child_layer")
            if any(r[2] for r in left+right):
                reasons.append("empty_layer_skipped")
            if any(r[3] for r in left+right):
                reasons.append("layer_outside_canvas_skipped")
            pairs = []
            for a in left:
                for b in right:
                    if a[2] or a[3] or b[2] or b[3]:
                        continue
                    pair_count += 1
                    _require(pair_count <= MAX_PAIRS, "resource_limit")
                    analysis = contact_between_alpha(a[4], b[4], max_gap=8)
                    ids = (a[0], b[0])
                    contacts = [item.to_contract(contact_id=f"{relation}:{a[0]}:{b[0]}:{index}",
                                joint_id=None, relation=relation, layer_ids=ids, flags=WARNINGS)
                                for index, item in enumerate(analysis.contacts)]
                    pairs.append({"layer_ids": list(ids), "contacts": contacts,
                                  "qa_flags": list(analysis.qa_flags), "min_lobe_area": analysis.min_lobe_area})
            relations.append({"relation": relation, "pairs": pairs, "reason_codes": reasons})
        document = {"schema": SCHEMA, "authority": "none", "candidate_sha256": canonical_sha256(candidate),
                "algorithm_profile": "raw-layer-contact-probe-v1", "coordinate_system": "psd_canvas",
                "canvas": deepcopy(candidate["canvas"]), "alpha_threshold_exclusive": 8,
                "max_gap_px": 8, "relations": relations}
        _require(len(json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                     .encode("utf-8")) <= MAX_OUTPUT_BYTES, "output_limit")
        return document
    except AlphaGeometryLimitError as exc:
        raise ValueError("benchmark_contact_probe_resource_limit") from exc
    except RgbaPngError as exc:
        raise ValueError("benchmark_contact_probe_image_invalid") from exc
    except ValueError as exc:
        if str(exc).startswith("benchmark_contact_probe_"):
            raise
        raise ValueError("benchmark_contact_probe_geometry_invalid") from exc
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("benchmark_contact_probe_input_invalid") from exc


def validate_contact_probe(candidate, images, document):
    expected = build_contact_probe(candidate, images)
    _require(type(document) is dict and document == expected
             and canonical_sha256(document) == canonical_sha256(expected), "mismatch")
    return deepcopy(expected)
