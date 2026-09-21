"""Collect source-sample failures even when order evaluation exits early."""
from copy import deepcopy


def collect(depth):
    records = deepcopy(depth.get('order', {}).get('failures', []))
    def key(row):
        return row.get('time'), row.get('reason_code'), tuple(sorted(row.get('pair', [])))
    seen = {key(row) for row in records}
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
            if key(row) not in seen:
                records.append(row); seen.add(key(row))
    return records


def categories(rows, limit=100):
    """Bound each category independently so early conflicts cannot hide limits."""
    groups = {}
    for row in rows:
        groups.setdefault(row['category'], []).append(row)
    return ({name: values[:limit] for name, values in groups.items()},
            {name: len(values)>limit for name, values in groups.items()})
