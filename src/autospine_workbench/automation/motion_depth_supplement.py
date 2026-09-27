"""Append-only CPU overlap supplements, outside the visual acceptance identity."""
import json
import re
from hashlib import sha256
from .animated_store import AnimatedStore
from .storage_io import canonical_bytes, directory, publish_document, read_document


def validate(report, registration, value, files):
    depth = value['receipt']['depth_audit']['depth']
    if (report.get('profile') != 'conservative-triangle-box-tiles-v1-experiment'
            or report.get('registration_sha256') != registration
            or report.get('artifact_sha256') != value['candidate_sha256']
            or report.get('skeleton_sha256') != sha256(files['skeleton.json']).hexdigest()
            or report.get('depth_sha256') != sha256(canonical_bytes(depth)).hexdigest()
            or report.get('authority') != 'none' or report.get('production_authorized') is not False):
        raise ValueError('motion_depth_supplement_identity')
    expected = {((p['arm_slot'], p['torso_slot']), s['tick']/1e6):
                s.get('overlap', {}) for p in depth['pairs'] for s in p['samples']}
    records = report.get('records')
    if not isinstance(records, list) or len(records) != len(expected):
        raise ValueError('motion_depth_supplement_samples')
    seen = set(); counts = dict(common_measured=0, overlap_mismatches=0,
                               recovered=0, lost_measurements=0, unmeasured=0)
    missing = []
    for row in records:
        key = (tuple(row['pair']), row['time'])
        if key in seen or key not in expected or row['previous'] != expected[key]:
            raise ValueError('motion_depth_supplement_samples')
        seen.add(key)
        old, new = row['previous'], row['current']
        if new.get('status') not in ('sampled', 'unmeasured'):
            raise ValueError('motion_depth_supplement_sample_status')
        if new['status'] == 'sampled' and (type(new.get('overlap_pixels')) is not int or new['overlap_pixels'] < 0):
            raise ValueError('motion_depth_supplement_pixels')
        common = old.get('status') == 'sampled' and new['status'] == 'sampled'
        counts['common_measured'] += common
        counts['overlap_mismatches'] += common and old['overlap_pixels'] != new['overlap_pixels']
        counts['recovered'] += old.get('status') == 'unmeasured' and new['status'] == 'sampled'
        counts['lost_measurements'] += old.get('status') == 'sampled' and new['status'] != 'sampled'
        counts['unmeasured'] += new['status'] == 'unmeasured'
        if new['status'] == 'unmeasured':
            missing.append(dict(time=row['time'], pair=row['pair']))
    if any(type(report.get(k)) is not int or report[k] != n for k, n in counts.items()):
        raise ValueError('motion_depth_supplement_counts')
    return dict(**counts, missing=missing, authority='none', selected=False,
                scope='cpu_overlap_source_samples_not_runtime_or_draw_order_acceptance')


def publish(state_root, folder, registration, value, files, report):
    validate(report, registration, value, files)
    digest = AnimatedStore(state_root).publish({'supplement.json': canonical_bytes(report)})
    root = directory(folder/'depth-supplements'/registration, create=True)
    if len(list(root.glob('*.json'))) >= 16 and not (root/(digest+'.json')).exists():
        raise ValueError('motion_depth_supplement_limit')
    publish_document(root/(digest+'.json'), {'digest': digest}, staging=folder/'staging')
    return digest


def summaries(state_root, folder, registration, value, files):
    root = folder/'depth-supplements'/registration
    if not root.exists():
        return []
    directory(root); paths = sorted(root.glob('*.json'))
    if len(paths) > 16:
        raise ValueError('motion_depth_supplement_limit')
    result = []
    for path in paths:
        if not re.fullmatch('[a-f0-9]{64}', path.stem) or read_document(path) != {'digest': path.stem}:
            raise ValueError('motion_depth_supplement_registration')
        report = json.loads(AnimatedStore(state_root).read_file(path.stem, 'supplement.json'))
        result.append(dict(digest=path.stem, **validate(report, registration, value, files)))
    return result
