"""Prepare a local Node-only provenance check from a hash-bound captured frame."""
import argparse
from base64 import b64encode
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes


def build(source, trace_path, output):
    if output.exists():
        raise ValueError('pixel_fixture_output_exists')
    report = json.loads((source/'report.json').read_bytes())
    digest = report['candidate_bundle_sha256']
    files = AnimatedStore(source/'isolated-store').read(digest)
    runtime = json.loads((source/'runtime/report.json').read_bytes())
    trace = json.loads(trace_path.read_bytes())
    if not (digest == trace['candidate_bundle_sha256'] == runtime['bundle_sha256']
            and sha256(files['skeleton.json']).hexdigest() == trace['skeleton_sha256']):
        raise ValueError('pixel_fixture_identity')
    shot = next(s for s in runtime['screenshots'] if s['sha256'] == trace['screenshot_sha256'])
    frame = next(r for r in runtime['results']
                 if r['animation'] == shot['animation'] and r['time'] == trace['time'])
    raw = (source/'runtime'/shot['file']).read_bytes()
    if sha256(raw).hexdigest() != shot['sha256']:
        raise ValueError('pixel_fixture_capture_changed')
    image = Image.open(BytesIO(raw)).convert('RGBA')
    if list(image.size) != trace['image_size']:
        raise ValueError('pixel_fixture_dimensions')
    for row in trace['rows']:
        if list(image.getpixel(tuple(row['pixel']))) != row['framebuffer_rgba']:
            raise ValueError('pixel_fixture_capture_pixel_changed')
    textures = {}
    for name, data in files.items():
        if name.startswith('textures/') and name.endswith('.png'):
            texture = Image.open(BytesIO(data)).convert('RGBA')
            textures[name] = dict(width=texture.width, height=texture.height,
                rgba=b64encode(texture.tobytes()).decode(), sha256=sha256(data).hexdigest())
    value = dict(candidate=digest, skeleton=json.loads(files['skeleton.json']),
        atlas=files['skeleton.atlas'].decode(), info=runtime['info'], textures=textures,
        runtime_sha256=runtime['runtime_sha256'], animation=frame['animation'],
        time=trace['time'], screenshot_sha256=shot['sha256'], rows=trace['rows'],
        image_size=trace['image_size'], authority='none', selected=False)
    output.write_bytes(canonical_bytes(value))
    print(json.dumps(dict(candidate=digest, samples=len(trace['rows']), textures=len(textures))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('trace', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.source, args.trace, args.output)
