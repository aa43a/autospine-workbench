"""Locate unresolved depth samples without assigning an invented occlusion side."""
import argparse
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore


def locate(document, field):
    mesh = document['skins'][0]['attachments'][field['arm']][field['arm']]
    count = len(mesh['uvs']) // 2
    influences = []
    data = mesh['vertices']; cursor = 0
    for _ in range(count):
        n = data[cursor]; cursor += 1
        weights = []
        for _ in range(n):
            index, x, y, weight = data[cursor:cursor+4]; cursor += 4
            if weight > 0:
                bone = document['bones'][index]
                weights.append(dict(bone=bone['name'], parent=bone.get('parent'), weight=weight))
        influences.append(weights)
    if cursor != len(data):
        raise ValueError('depth_mesh_vertex_count')
    rows = field['rows']; previous = -math.inf
    runs = {}; issues = []
    for frame_index, row in enumerate(rows):
        time = row['time']; values = row['depth_values']
        if not math.isfinite(time) or time <= previous or len(values) != count:
            raise ValueError('depth_schedule_invalid')
        previous = time
        if any(v is not None and not math.isfinite(v) for v in values):
            raise ValueError('depth_value_nonfinite')
        for vertex, value in enumerate(values):
            if value is None:
                if vertex not in runs:
                    runs[vertex] = dict(vertex=vertex, first_sample=frame_index,
                                        start_time=time, end_time=time, sample_count=0)
                runs[vertex]['end_time'] = time
                runs[vertex]['sample_count'] += 1
            elif vertex in runs:
                issues.append(runs.pop(vertex))
    issues.extend(runs.values())
    triangles = mesh['triangles']
    for issue in issues:
        vertex = issue['vertex']
        issue.update(influences=influences[vertex],
                     triangles=[i//3 for i in range(0, len(triangles), 3)
                                if vertex in triangles[i:i+3]])
    return dict(candidate=field['candidate'], arm=field['arm'], authority='none',
                selected=False, status='depth_unknown' if issues else 'sampled_depth_available',
                scope='sampled_unknown_runs_and_influences_not_causal_attribution',
                unknown_vertices=len({r['vertex'] for r in issues}),
                unknown_vertex_samples=sum(r['sample_count'] for r in issues),
                issues=sorted(issues, key=lambda r: (r['start_time'], r['vertex'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'field', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    field = json.loads(args.field.read_bytes())
    receipt = json.loads((args.source/'report.json').read_bytes())
    if field['candidate'] != receipt['candidate_bundle_sha256']:
        raise ValueError('depth_candidate_mismatch')
    files = AnimatedStore(args.source/'isolated-store').read(field['candidate'])
    report = locate(json.loads(files['skeleton.json']), field)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != 'issues'}))


if __name__ == '__main__':
    main()
