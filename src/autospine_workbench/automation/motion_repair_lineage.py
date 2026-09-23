"""Carry immutable repair decisions into a descendant export without accepting them."""
from hashlib import sha256
import json
from .storage_io import canonical_bytes


def carry(source, repair):
    raw = source.get('motion-repair-provenance.json')
    expected = repair.get('parent_repair_sha256')
    if raw is None:
        if expected is not None:
            raise ValueError('motion_repair_parent_provenance_missing')
        return {}
    if sha256(raw).hexdigest() != expected:
        raise ValueError('motion_repair_parent_provenance_changed')
    history = {n: v for n, v in source.items() if n.startswith('repair-history/')}
    if len(history) >= 32:
        raise ValueError('motion_repair_history_limit')
    for name, value in history.items():
        if name != 'repair-history/' + sha256(value).hexdigest() + '.json':
            raise ValueError('motion_repair_history_identity')
    record = canonical_bytes(dict(parent_artifact_sha256=repair['parent_artifact_sha256'],
        parent_job_id=repair['parent_job_id'], provenance=json.loads(raw),
        report=json.loads(source['motion-repair.json']), authority='none', selected=False))
    history['repair-history/' + sha256(record).hexdigest() + '.json'] = record
    return history
