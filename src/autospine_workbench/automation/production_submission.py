"""Reserve child identities before dispatch; ordinary callers keep random IDs."""
from contextlib import contextmanager
from contextvars import ContextVar
import re
from uuid import uuid4

from .pipeline_run import PipelineRunError

_reservation = ContextVar('production_child_reservation', default=None)


@contextmanager
def reserved_child(job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r'(job|motion)-[a-f0-9]{32}', job_id):
        raise PipelineRunError('production_child_invalid')
    token = _reservation.set(dict(job_id=job_id, consumed=False))
    try:
        yield
    finally:
        _reservation.reset(token)


def child_id(prefix):
    reservation = _reservation.get()
    if reservation is None:
        return prefix + uuid4().hex
    if reservation['consumed'] or not reservation['job_id'].startswith(prefix):
        raise PipelineRunError('production_child_reservation_conflict')
    reservation['consumed'] = True
    return reservation['job_id']
