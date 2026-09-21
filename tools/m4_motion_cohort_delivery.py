"""Verify frozen candidate downloads, preserving per-candidate delivery receipts."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from m4_motion_cohort import digest
from m4_motion_delivery_check import run


def inventory(plan, state):
    if state.get('plan_sha256') != digest(plan):
        raise ValueError('cohort_plan_identity_mismatch')
    rows = []
    for motion in plan['motions']:
        for character in plan['characters']:
            key = motion['id'] + '/' + character['id']
            job = state['cells'].get(key, {})
            if job.get('status') != 'succeeded':
                raise ValueError('delivery_candidate_not_complete:' + key)
            identifier = job['job_id']; artifact = job['result']['artifact_sha256']
            if not re.fullmatch(r'motion-[a-f0-9]{32}', identifier) or not re.fullmatch(r'[a-f0-9]{64}', artifact):
                raise ValueError('delivery_candidate_identity_invalid')
            rows.append(dict(cell=key, job_id=identifier, artifact_sha256=artifact))
    if len({r['job_id'] for r in rows}) != len(rows):
        raise ValueError('delivery_duplicate_candidate')
    return rows


def check(receipt, row, plan_hash):
    if (receipt.get('plan_sha256') != plan_hash or receipt.get('cell') != row['cell']
            or receipt.get('job_id') != row['job_id']
            or receipt.get('artifact_sha256') != row['artifact_sha256']):
        raise ValueError('delivery_receipt_identity_mismatch')


def collect(plan, state, root, deliver=run, progress=print):
    rows = inventory(plan, state); plan_hash = digest(plan)
    root.mkdir(parents=True, exist_ok=True)
    receipts = []
    for row in rows:
        path = root / (row['job_id'] + '.json')
        if path.exists():
            receipt = json.loads(path.read_text(encoding='utf-8'))
            check(receipt, row, plan_hash)
            progress(row['cell'] + ' historical_receipt')
        else:
            receipt = deliver(row['job_id'])
            receipt.update(cell=row['cell'], plan_sha256=plan_hash,
                           verified_at=datetime.now(timezone.utc).isoformat())
            check(receipt, row, plan_hash)
            with path.open('x', encoding='utf-8') as handle:
                json.dump(receipt, handle, ensure_ascii=False, indent=2)
            progress(row['cell'] + ' verified_download')
        receipts.append(receipt)
    return dict(profile='frozen-motion-cohort-delivery-v1', plan_sha256=plan_hash,
                required=len(rows), verified=len(receipts), receipts=receipts,
                scope='delivery_at_receipt_times_not_quality_or_new_runtime_capture',
                authority='none', production_authorized=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path); parser.add_argument('state', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    plan, state = [json.loads(p.read_text(encoding='utf-8')) for p in (args.plan, args.state)]
    result = collect(plan, state, args.output, progress=lambda s: print(s, flush=True))
    # Summary is reproducible; immutable per-job receipts retain their own times.
    (args.output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
