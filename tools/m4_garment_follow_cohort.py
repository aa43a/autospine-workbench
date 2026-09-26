"""Compare declared skirt root following on immutable whole-character candidates."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from m4_attachment_root_transport_probe import run as bake
from m4_corrective_geometry_check import prepare
from m4_skirt_waist_support import fixed_region
from autospine_workbench.targets.character43.skirt_motion_contact import transport
import math


def run(state, sources, output):
    output.mkdir(parents=True, exist_ok=False); rows = []
    for source in sources:
        request = json.loads((source/'request.json').read_bytes())
        receipt = json.loads((source/'report.json').read_bytes())
        original = AnimatedStore(state).read(request['character_sha256'])
        files = AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
        doc = json.loads(files['skeleton.json']); bind = json.loads(original['skeleton.json'])
        if any(doc[k] != bind[k] for k in ('bones', 'skins', 'slots')):
            raise ValueError('garment_cohort_bind_changed')
        trial = json.loads(original['skirt-trial.json'])
        if trial.get('waist_driver') != 'reviewed-chest-v1':
            raise ValueError('garment_cohort_waist_owner_undeclared')
        # Read existing generated-chain declarations, not names/coordinates guessed from the picture.
        roots = [f"{row['layer_id']}-{chain['id']}_upper" for row in trial['rows']
                 for chain in row['mesh']['helper_chains']]
        selected = {row['layer_id'] for row in trial['rows']}
        folder = output/source.name
        print(json.dumps(dict(source=source.name, stage='bake', roots=roots)), flush=True)
        bake(source, folder, roots)
        report = json.loads((folder/'report.json').read_bytes())
        if {r['slot'] for r in report['rows']} != selected:
            raise ValueError('garment_cohort_unexpected_affected_attachment')
        print(json.dumps(dict(source=source.name, stage='full_geometry')), flush=True)
        _, checked = prepare(source, folder)
        after = json.loads((folder/'skeleton.json').read_bytes())
        # Same immutable parent sampling grid on both sides, including new keys and midpoints.
        times = checked['sample_times']
        from autospine_workbench.targets.character43.numeric_reference import write
        from autospine_workbench.targets.character43.deformation_qa import inspect
        baseline = write(dict(files), dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
            animations={'external-motion': [dict(time=t, vertices=sample(doc, 'external-motion', t)[0]) for t in times]}))
        setup = json.loads(files['rig-setup-reference.json'])['vertices']
        before_qa = inspect(baseline, setup_vertices=setup)
        contacts = []
        for slot in sorted(selected):
            _, support = fixed_region(original, files, slot)
            peaks = [0., 0.]
            for time in times:
                for index, document in enumerate((doc, after)):
                    points = sample(document, 'external-motion', time)[0]
                    for a in support['anchors']:
                        separation = math.dist(transport(points[slot], a['skirt_anchor']),
                                               transport(points[a['torso']], a['torso_anchor']))
                        peaks[index] = max(peaks[index], separation)
            contacts.append(dict(slot=slot, anchors=len(support['anchors']), before_max_px=peaks[0], after_max_px=peaks[1]))
        value = dict(report, source=source.name, source_candidate=receipt['candidate_bundle_sha256'],
            character_sha256=request['character_sha256'], motion_identity=request['motion_identity'],
            yaw=request.get('projection', {}).get('yaw_degrees'),
            frames=len(times), before=before_qa, after=checked['geometry'], waist_contact=contacts,
            runtime='not_run', visual='not_reviewed', production_authorized=False)
        (folder/'comparison.json').write_bytes(canonical_bytes(value)); rows.append(value)
        print(json.dumps(dict(source=source.name, stage='done', frames=len(times),
            before=[r for r in before_qa['records'] if r['slot'] in selected],
            after=[r for r in checked['geometry']['records'] if r['slot'] in selected], contacts=contacts)), flush=True)
        (output/'summary.json').write_bytes(canonical_bytes(dict(rows=rows, authority='none', selected=False)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('state', type=Path); p.add_argument('output', type=Path)
    p.add_argument('sources', type=Path, nargs='+'); a = p.parse_args()
    run(a.state, a.sources, a.output)
