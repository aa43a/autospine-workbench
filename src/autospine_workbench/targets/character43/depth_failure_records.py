"""Collect source-sample failures even when order evaluation exits early."""
from copy import deepcopy


def collect(depth):
    records = deepcopy(depth.get('order', {}).get('failures', []))
    def key(row):
        return row.get('time'), row.get('reason_code'), tuple(sorted(row.get('pair', [])))
    seen = {key(row) for row in records}
    def append(row):
        if key(row) not in seen:
            records.append(row); seen.add(key(row))
    for pair in depth.get('pairs', []):
        for sample in pair.get('samples', []):
            overlap = sample.get('overlap', {})
            if overlap.get('status') != 'unmeasured':
                continue
            row = dict(time=sample['tick']/1e6,
                reason_code=overlap.get('reason_code', 'depth_overlap_unmeasured'),
                pair=[pair['arm_slot'], pair['torso_slot']])
            if overlap.get('raster_budget'):
                row['raster_budget'] = deepcopy(overlap['raster_budget'])
            append(row)
    regional = depth.get('regional', {})
    groups = [(r.get('pair'), r) for r in regional.get('refinement', {}).get('rows', [])]
    for section, other in [('cloth_constraints', 'cloth'), ('limb_constraints', 'leg')]:
        for pair in (regional.get(section) or {}).get('pairs', []):
            groups.extend(([pair['arm'], pair[other]], r) for r in pair.get('rows', []))
    for pair, row in groups:
        for check in row.get('checks', []):
            if check.get('status') != 'unmeasured':
                continue
            failure = dict(time=check.get('time'),
                reason_code=check.get('reason_code', 'regional_depth_unmeasured'))
            if pair:
                failure['pair'] = list(pair)
            if check.get('raster_budget'):
                failure['raster_budget'] = deepcopy(check['raster_budget'])
            append(failure)
    return records


def categories(rows, limit=100):
    """Bound each category independently so early conflicts cannot hide limits."""
    groups = {}
    for row in rows:
        groups.setdefault(row['category'], []).append(row)
    return ({name: values[:limit] for name, values in groups.items()},
            {name: len(values)>limit for name, values in groups.items()})
