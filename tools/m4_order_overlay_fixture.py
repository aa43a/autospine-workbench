"""Prepare an isolated dynamic-order stress case from an existing Runtime scene.

Injected order keys are diagnostics, never user decisions or repaired assets.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.spine42_draw_order_offsets import encode_spine42_draw_order_offsets
from autospine_workbench.targets.character43.region_order_candidate import build
from autospine_workbench.targets.character43.region_order_interval import duration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--slot', required=True)
    parser.add_argument('--reference', required=True)
    args = parser.parse_args()
    raw = args.scene.read_bytes(); scene = json.loads(raw)
    scene = deepcopy(scene); doc = scene['skeleton']
    animation = next(iter(doc['animations']))
    length = duration(doc['animations'][animation])
    if length <= 0:
        raise ValueError('positive_duration_required')
    names = [s['name'] for s in doc['slots']]
    if args.slot not in names or args.reference not in names or args.slot == args.reference:
        raise ValueError('distinct_existing_slots_required')
    # Change non-selected relative order too, testing that it survives the edit.
    orders = [names[-1:] + names[:-1], names[1:] + names[:1], list(reversed(names))]
    doc['animations'][animation]['drawOrder'] = [
        dict(time=t, offsets=encode_spine42_draw_order_offsets(names, order))
        for t, order in zip([0, length/2, 3*length/4], orders)]
    candidate, report = build(doc, args.slot, [0], args.reference, 'after',
                              animation=animation, interval=[length/4, 3*length/4])
    report['diagnostic_fixture'] = dict(source_scene_sha256=sha256(raw).hexdigest(),
        injected_order_keys=True, user_decision=False, production_candidate=False)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('source', scene), ('candidate', dict(scene, skeleton=candidate)), ('report', report)]:
        (args.output/(name+'.json')).write_text(json.dumps(value), encoding='utf-8')
    print(json.dumps(report['diagnostic_fixture']))


if __name__ == '__main__':
    main()
