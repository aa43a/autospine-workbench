"""Prepare immutable native-pixel probes for official Runtime material visibility."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_runtime_depth_review import map_pixels


def prepare(diagnostic, capture, output):
    raw = diagnostic.read_bytes(); report = json.loads(raw)
    runtime_raw = (capture/'partitioned/report.json').read_bytes()
    runtime = json.loads(runtime_raw)
    files = AnimatedStore(capture/'isolated-store').read(runtime['bundle_sha256'])
    if (runtime.get('passed') is not True or report.get('pixel_locations') is not True
            or sha256(files['skeleton.json']).hexdigest() != report['skeleton_sha256']):
        raise ValueError('visibility_source_identity')
    doc = json.loads(files['skeleton.json']); info = runtime['info']
    # Isolated rendering cannot preserve clipping or non-normal compositing.
    if any(s.get('blend', 'normal') != 'normal' for s in doc['slots']):
        raise ValueError('visibility_blend_unsupported')
    if any(a.get('type') == 'clipping' for skin in doc['skins']
           for attachments in skin['attachments'].values() for a in attachments.values()):
        raise ValueError('visibility_clipping_unsupported')
    rows = []
    for row in report['rows']:
        h = row['hypotheses'][-1]
        if h['status'] != 'requires_partition_or_more_depth': continue
        if h['time'] != row['time'] or h['pair'] != [row['region'], row['body']]:
            raise ValueError('visibility_probe_identity')
        frame = next(f for f in runtime['results'] if f['animation'] == 'external-motion' and f['time'] == row['time'])
        shot = next(s for s in runtime['screenshots'] if s['animation'] == frame['animation'] and s['index'] == frame['index'])
        name = Path(shot['file'])
        if name.is_absolute() or '..' in name.parts: raise ValueError('visibility_image_path')
        png = (capture/'partitioned'/name).read_bytes()
        if sha256(png).hexdigest() != shot['sha256']: raise ValueError('visibility_image_identity')
        points = []
        for kind, values in h['pixel_locations'].items():
            mapped = map_pixels(values, info, (info['width'], info['height']))
            if len(mapped) != h['counts'][kind] or len(set(mapped)) != len(mapped):
                raise ValueError('visibility_pixel_inventory')
            points.extend(dict(x=x, y=y, kind=kind) for x, y in mapped)
        rows.append(dict(time=row['time'], region=row['region'], body=row['body'],
                         points=points, draw_order=frame['draw_order'], screenshot_sha256=shot['sha256'],
                         screenshot='data:image/png;base64,'+base64.b64encode(png).decode()))
    if not rows or len(rows) > 32 or sum(len(r['points']) for r in rows) > 100000:
        raise ValueError('visibility_probe_budget')
    value = dict(schema='autospine.runtime-visibility-fixture/v1', skeleton=doc,
                 atlas=files['skeleton.atlas'].decode(), info=info, rows=rows,
                 textures={n: 'data:image/png;base64,'+base64.b64encode(b).decode()
                           for n, b in files.items() if n.startswith('textures/') and n.endswith('.png')},
                 source_artifact_sha256=report['source_artifact_sha256'],
                 skeleton_sha256=report['skeleton_sha256'], bundle_sha256=runtime['bundle_sha256'],
                 diagnostic_sha256=sha256(raw).hexdigest(), runtime_report_sha256=sha256(runtime_raw).hexdigest(),
                 runtime_sha256=runtime['runtime_sha256'], runtime_version=runtime['runtime_version'],
                 authority='none', production_authorized=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream: stream.write(canonical_bytes(value))
    print(json.dumps(dict(frames=len(rows), pixels=sum(len(r['points']) for r in rows))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('diagnostic', 'capture', 'output'): parser.add_argument(name, type=Path)
    args = parser.parse_args(); prepare(args.diagnostic, args.capture, args.output)
