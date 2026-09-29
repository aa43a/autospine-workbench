"""Monotonic, persisted stage timings for a single isolated build worker."""
import os
import time

from .motion_intake_process import progress
from .storage_io import canonical_bytes


class BuildTiming:
    def __init__(self, folder, *, clock=time.perf_counter):
        self.folder, self.clock = folder, clock
        self.started = self.changed = clock()
        self.active = None
        self.stages = {}
        self.status = 'running'

    def snapshot(self):
        now = self.clock()
        stages = {key: dict(value) for key, value in self.stages.items()}
        if self.active:
            stages[self.active]['seconds'] += max(0., now - self.changed)
        return dict(schema='autospine.build-timing/v1', status=self.status,
                    elapsed_seconds=round(max(0., now - self.started), 3),
                    active_step=self.active,
                    stages=[dict(step=key, seconds=round(value['seconds'], 3), calls=value['calls'])
                            for key, value in stages.items()])

    def _persist(self, value):
        temporary = self.folder / 'build-timing.tmp'
        try:
            temporary.write_bytes(canonical_bytes(value))
            os.replace(temporary, self.folder / 'build-timing.json')
        except OSError:
            # Timing is telemetry: Windows readers must not fail a valid build.
            pass

    def __call__(self, step, detail=None):
        now = self.clock()
        if self.active:
            self.stages[self.active]['seconds'] += max(0., now - self.changed)
        self.active, self.changed = step, now
        self.stages.setdefault(step, dict(seconds=0., calls=0))['calls'] += 1
        value = self.snapshot()
        self._persist(value)
        progress(self.folder, step, detail, timing=value)

    def finish(self, status):
        if status not in {'completed', 'failed'}:
            raise ValueError('motion_build_timing_status')
        value = self.snapshot()
        self.status = value['status'] = status
        value['active_step'] = None
        self._persist(value)
        if self.active:
            progress(self.folder, self.active, timing=value)
        return value
