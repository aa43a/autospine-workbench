"""Check whether fixed-boundary interior controls can repair a real candidate."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.pose_refinement_feasibility import inspect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scene', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--slot', action='append', required=True)
    parser.add_argument('--animation', required=True)
    args = parser.parse_args()
    scene = json.loads(args.scene.read_bytes())
    document = scene['skeleton']
    animation = document['animations'][args.animation]
    def times(value):
        if isinstance(value, dict):
            return [v for k, v in value.items() if k == 'time'] + [
                t for k, v in value.items() if k != 'time' for t in times(v)]
        if isinstance(value, list):
            return [t for child in value for t in times(child)]
        return []
    knots = sorted(set([0.] + times(animation)))
    checks = sorted(set(knots + [(a+b)/2 for a, b in zip(knots, knots[1:])]))
    setup_document = deepcopy(document)
    setup_document['animations'] = {'setup': {}}
    setup = sample(setup_document, 'setup', 0)[0]
    results = {slot: [] for slot in args.slot}
    for time in checks:
        points = sample(document, args.animation, time)[0]
        for slot in args.slot:
            flat = document['skins'][0]['attachments'][slot][slot]['triangles']
            triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
            result = inspect(setup[slot], points[slot], triangles, list(range(len(triangles))))
            results[slot].append(dict(time=time, **result))
    summary = {slot: dict(checked_frames=len(rows),
        impossible_frames=sum(bool(r['counterexamples']) for r in rows),
        inverted_parent_samples=sum(c['area_ratio'] <= 0 for r in rows for c in r['counterexamples']),
        first_counterexample=next((dict(time=r['time'], **r['counterexamples'][0])
                                   for r in rows if r['counterexamples']), None))
        for slot, rows in results.items()}
    report = dict(source_path=str(args.scene.resolve()), source_artifact=scene.get('artifact_sha256'),
        document_sha256=canonical_sha256(document), animation=args.animation, summary=summary,
        records=results, authority='none', selected=False,
        scope='python_pose_samples_and_fixed_boundary_necessary_conditions_not_runtime_or_visual_acceptance')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
