"""Deterministic preview package with sampled player data and editor image paths."""

from copy import deepcopy
import hashlib
from io import BytesIO

from ..asset.joints.partition_pixels import png
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_pose import world
from .storage_io import canonical_bytes


def package_preview(inputs, compiled):
    from PIL import Image

    inputs = compiled.get("expanded_inputs", inputs)
    doc = compiled["document"]
    files = {"skeleton.json": canonical_bytes(doc), "motion.json": canonical_bytes(compiled["motion"]),
             "qa.json": canonical_bytes(compiled["qa"])}
    original = {r["layer_id"]: r for r in inputs.candidate["layers"]}
    attachments = doc["skins"][0]["attachments"]
    regions = deepcopy(compiled["regions"])
    pages, layers = [], []
    for region in regions:
        name = region["id"]
        raw = inputs.images[name]
        if hashlib.sha256(raw).hexdigest() != original[name]["image_sha256"]:
            raise ValueError("animated_image_changed")
        attachment = attachments[name][name]
        w, h = attachment["width"], attachment["height"]
        with Image.open(BytesIO(raw)) as image:
            if image.size != (w, h):
                raise ValueError("animated_image_dimensions_changed")
            page = Image.new("RGBA", (w + 4, h + 4))
            page.paste(image.convert("RGBA"), (2, 2))
            page_bytes = png("RGBA", page.size, page.tobytes())
        texture = "textures/" + name + ".png"
        image_path = "images/" + name + ".png"
        files[texture] = page_bytes
        files[image_path] = raw
        files["editor/" + image_path] = raw
        pages.append(f"{texture}\nsize: {w+4},{h+4}\nfilter: Linear,Linear\npma: false\nrepeat: none\n"
                     f"{name}\nbounds: 2,2,{w},{h}\n")
        uvs = list(zip(attachment["uvs"][::2], attachment["uvs"][1::2]))
        region["expected_page_uvs"] = [[(2 + u*w)/(w+4), (2 + v*h)/(h+4)] for u, v in uvs]
        triangles = attachment["triangles"]
        layers.append({"id": name, "image": image_path, "uvs": uvs,
                       "triangles": [triangles[i:i+3] for i in range(0, len(triangles), 3)]})
    files["skeleton.atlas"] = "\n".join(pages).encode()
    editor = deepcopy(doc)
    editor["skeleton"]["images"] = "./images/"
    files["editor/skeleton.json"] = canonical_bytes(editor)
    frames = []
    for frame in range(61):
        positions = world(doc, frame/30)
        frames.append({"time": frame/30, "vertices": {
            name: [[round(x, 7), round(-y, 7)] for x, y in points] for name, points in positions.items()
        }})
    files["playback.json"] = canonical_bytes({"fps": 30, "duration": 2,
        "canvas": inputs.candidate["canvas"], "layers": layers, "frames": frames,
        "renderer": "sampled_cpu_diagnostic", "authority": "none"})
    scope = {"schema": "autospine.workbench-animated-preview/v1", "authority": "none",
             "production_authorized": False, "target": "4.3.26", "status": "needs_review",
             "full_character_animation": False, "animation": compiled["motion"]["clip"],
             "regions": regions, "bake_qa": compiled["qa"]["geometry"],
             "source_addresses": deepcopy(inputs.source_addresses),
             "summary": compiled["summary"], "review_items": compiled["review_items"],
             "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())}}
    if 'visibility_profile' in compiled:
        scope['visibility_profile'] = compiled['visibility_profile']
    files["preview-manifest.json"] = canonical_bytes(scope)
    return files


def files_digest(files):
    return canonical_sha256({name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())})
