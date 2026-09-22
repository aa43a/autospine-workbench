"""Locate observed mixed depth on immutable source UVs and structural weight groups."""
import argparse
import base64
from collections import Counter
from hashlib import sha256
import json
from io import BytesIO
from pathlib import Path
from PIL import Image

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.depth_partition_trace import classify, labels


def owners(document, mesh):
    values = []; data = iter(mesh['vertices'])
    for count in data:
        weights = Counter()
        for _ in range(count):
            index, x, y, weight = next(data), next(data), next(data), next(data)
            weights[document['bones'][index]['name']] += weight
        values.append(weights)
    result = []
    for i in range(0, len(mesh['triangles']), 3):
        total = Counter()
        for vertex in mesh['triangles'][i:i+3]: total.update(values[vertex])
        # Dominant influence is a localization label, never semantic approval.
        result.append(sorted(total, key=lambda bone: (-total[bone], bone))[0])
    return result


def summarize(ownership, samples):
    labels(len(ownership), samples)  # Reject partial, duplicate, or invalid trace inventories.
    output = {bone: Counter() for bone in set(ownership)}
    frames = []
    for row in samples:
        groups = {bone: Counter() for bone in output}
        marked = []
        for triangle, counts in row['triangles'].items():
            groups[ownership[triangle]].update(counts)
            state = classify(counts)
            if state != 'N': marked.append([triangle, state])
        for bone, counts in groups.items(): output[bone][classify(counts)] += 1
        frames.append(dict(time=row['time'], marked=marked))
    return dict(groups={k: dict(v) for k,v in sorted(output.items())}, frames=frames)


def run(source, traces, output):
    receipt = json.loads((source/'report.json').read_bytes())
    trace_receipt = json.loads((traces/'report.json').read_bytes())
    digest = receipt['candidate_bundle_sha256']
    if trace_receipt['candidate'] != digest or not trace_receipt['baked_torso_plane']:
        raise ValueError('structure_trace_identity_mismatch')
    files = AnimatedStore(source/'isolated-store').read(digest)
    document = json.loads(files['skeleton.json'])
    raw = (traces/'triangle-traces.json').read_bytes(); observations = json.loads(raw)
    depth = json.loads((traces/'depth.json').read_bytes())
    if depth['candidate_bundle_sha256'] != digest:
        raise ValueError('structure_depth_identity_mismatch')
    rows = []
    for arm, samples in observations.items():
        expected = set()
        for pair in depth['pairs']:
            if pair['arm_slot'] != arm: continue
            for item in pair['samples']:
                expected.add((pair['torso_slot'], item['tick']/1e6))
                if item.get('interval_sample'):
                    expected.add((pair['torso_slot'], item['interval_sample']['tick']/1e6))
        if len(samples) != len(expected) or {(s['body'], s['time']) for s in samples} != expected:
            raise ValueError('structure_trace_incomplete')
        if len({s['body'] for s in samples}) != 1 or any(s['status']=='unmeasured' for s in samples):
            raise ValueError('structure_trace_unsupported')
        for sample in samples: sample['triangles'] = {int(k): v for k,v in sample['triangles'].items()}
        mesh = document['skins'][0]['attachments'][arm][arm]
        result = summarize(owners(document, mesh), samples)
        image = files['images/'+mesh.get('path', arm)+'.png']
        with Image.open(BytesIO(image)) as texture: width, height = texture.size
        rows.append(dict(slot=arm, uvs=mesh['uvs'], triangles=mesh['triangles'], **result,
                         width=width, height=height,
                         texture='data:image/png;base64,'+base64.b64encode(image).decode()))
    report = dict(authority='none', selected=False, candidate=digest,
                  trace_sha256=sha256(raw).hexdigest(), rows=rows,
                  scope='dominant_weight_localization_not_semantic_partition_or_order_approval')
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    html = Path('tools/m4-reach-structure-review.html').read_text(encoding='utf-8')
    payload = json.dumps(report, ensure_ascii=False).replace('<', '\\u003c')
    (output/'index.html').write_text(html.replace('/*DATA*/', payload), encoding='utf-8')
    print(json.dumps({r['slot']: r['groups'] for r in rows}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'traces', 'output'): parser.add_argument(name, type=Path)
    args = parser.parse_args(); run(args.source, args.traces, args.output)
