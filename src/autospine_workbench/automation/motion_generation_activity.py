"""Read-only activity observations; silence never changes task lifecycle state."""
import math
import stat
import time


def _observation(path, now):
    try:
        value = path.lstat()
        if (not stat.S_ISREG(value.st_mode)
                or getattr(value, 'st_file_attributes', 0) & 0x400
                or not math.isfinite(value.st_mtime) or value.st_mtime > now):
            return None
        return dict(age_seconds=int(now - value.st_mtime), bytes=value.st_size)
    except OSError:
        return None


def activity(folder, *, now=None):
    now = time.time() if now is None else now
    if not math.isfinite(now):
        return None
    stage = _observation(folder / 'progress.json', now)
    output = _observation(folder / 'generation.log', now)
    return dict(stage_elapsed_seconds=stage['age_seconds'] if stage else None,
                log_age_seconds=output['age_seconds'] if output else None,
                log_bytes=output['bytes'] if output else None,
                meaning='observed_activity_not_completion_or_health')
