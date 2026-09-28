"""Expand an immutable visibility fixture to every prior captured source/midpoint frame."""
import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from autospine_workbench.automation.storage_io import canonical_bytes


def expand(fixture_path, capture, output):
    if output.exists(): raise ValueError('output_exists')
    raw = fixture_path.read_bytes(); fixture = json.loads(raw)
    capture_raw = (capture/'report.json').read_bytes(); report = json.loads(capture_raw)
    if (sha256(capture_raw).hexdigest() != fixture['runtime_report_sha256']
            or report['bundle_sha256'] != fixture['bundle_sha256'] or report['info'] != fixture['info']
            or report.get('passed') is not True): raise ValueError('order_sequence_identity')
    pairs = {(r['region'],r['body']) for r in fixture['rows']}
    if len(pairs) != 1: raise ValueError('order_sequence_single_pair_required')
    region, body = next(iter(pairs)); rows = []
    frames = report['results']; shots = {(s['animation'],s['index']):s for s in report['screenshots']}
    if not 1 <= len(frames) <= 1023 or any(f['animation'] != 'external-motion' for f in frames):
        raise ValueError('order_sequence_frame_inventory')
    if any(b['time'] <= a['time'] for a,b in zip(frames,frames[1:])): raise ValueError('order_sequence_time_order')
    for index, frame in enumerate(frames):
        shot = shots[frame['animation'],frame['index']]; name = Path(shot['file'])
        if name.is_absolute() or '..' in name.parts: raise ValueError('order_sequence_image_path')
        image_raw = (capture/name).read_bytes()
        if sha256(image_raw).hexdigest() != shot['sha256']: raise ValueError('order_sequence_image_changed')
        image = Image.open(BytesIO(image_raw)).convert('RGBA')
        if image.size != (fixture['info']['width'],fixture['info']['height']): raise ValueError('order_sequence_image_size')
        # One opaque anchor is enough for negative controls; the renderer checks the entire image.
        pixel = next((i for i,a in enumerate(image.getchannel('A').tobytes()) if a == 255), None)
        if pixel is None: raise ValueError('order_sequence_opaque_anchor_missing')
        rows.append(dict(time=frame['time'],region=region,body=body,draw_order=frame['draw_order'],
            points=[dict(x=pixel%image.width,y=pixel//image.width,kind='frame_reference_anchor')],
            screenshot_sha256=shot['sha256'],screenshot='data:image/png;base64,'+base64.b64encode(image_raw).decode(),
            capture_images=index%16 == 0 or index == len(frames)-1))
    fixture.update(rows=rows,whole_frame_trial=True,parent_fixture_sha256=sha256(raw).hexdigest(),
                   scope='all_existing_capture_frames_fixed_order_trial_not_animation_acceptance')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream: stream.write(canonical_bytes(fixture))
    print(json.dumps(dict(frames=len(rows),start=rows[0]['time'],end=rows[-1]['time'])))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('fixture','capture','output'): p.add_argument(key,type=Path)
    a = p.parse_args(); expand(a.fixture,a.capture,a.output)
