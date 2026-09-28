"""Audit every frozen candidate's current immutable bytes, export and Runtime identity."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.automation.animated_store import AnimatedStore


def audit(snapshot, state):
    rows = snapshot['rows']
    expected = {(motion, character) for motion in
        ('breathing', 'walking', 'wave', 'raise-arms', 'turn', 'squat', 'boxing', 'reach')
        for character in ('alice', 'huiye', 'hongmeiling')}
    assert len(rows) == 24 and {(r['motion'], r['character']) for r in rows} == expected
    store = AnimatedStore(state)
    records = []
    for row in rows:
        assert row['status'] == 'verified'
        files = store.read(row['artifact_sha256'])
        required = {'skeleton.json', 'skeleton.atlas', 'motion-ir.json',
                    'motion-contact.json', 'motion-depth.json', 'motion-review.json'}
        assert required <= files.keys(), required - files.keys()
        skeleton = json.loads(files['skeleton.json'])
        assert skeleton['skeleton']['spine'] == '4.3.26'
        assert 'external-motion' in skeleton['animations']
        # Player HTML is served by the workbench, not stored inside older bundles.
        with urlopen(f"http://127.0.0.1:8918/api/motions/{row['job_id']}/view/player.html", timeout=120) as response:
            player = response.read()
        with urlopen(f"http://127.0.0.1:8918/api/motions/{row['job_id']}/view/player-assets/context.json", timeout=120) as response:
            player_context = json.load(response)
        assert player_context['artifact_sha256'] == row['artifact_sha256']
        runtime_raw = (state/'jobs/motion-intake-v1'/row['job_id']/'runtime/report.json').read_bytes()
        runtime = json.loads(runtime_raw)
        assert runtime['bundle_sha256'] == row['artifact_sha256']
        assert player_context['runtime_sha256'] == runtime['runtime_sha256']
        assert runtime['passed'] is True and runtime['results']
        stages = row['review']['readiness']['stages']
        assert {'投影', '几何', '接触', '遮挡', 'Runtime'} <= {s['stage'] for s in stages}
        records.append(dict(motion=row['motion'], character=row['character'], job_id=row['job_id'],
            artifact_sha256=row['artifact_sha256'], files=len(files), export_version='4.3.26',
            runtime_version=runtime.get('runtime_version'), runtime_frames=len(runtime['results']),
            runtime_sha256=sha256(runtime_raw).hexdigest(),
            skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
            served_player_sha256=sha256(player).hexdigest(),
            technical_status=row['review']['readiness']['status']))
        print(json.dumps(dict(motion=row['motion'], character=row['character'], files=len(files))), flush=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--state', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output_exists')
    raw = args.snapshot.read_bytes()
    result = dict(profile='m4-fixed-current-bundle-audit-v1', checked_at=datetime.now(timezone.utc).isoformat(),
        snapshot_sha256=sha256(raw).hexdigest(), rows=audit(json.loads(raw), args.state),
        scope='all_current_bundle_bytes_and_historical_runtime_identity_not_new_capture_or_quality_pass',
        new_visual_acceptance=False, production_authorized=False)
    with args.output.open('x', encoding='utf8') as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
