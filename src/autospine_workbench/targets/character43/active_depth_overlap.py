"""Whole-slot alpha overlap for switched attachments; no surface-depth inference."""
from copy import deepcopy

from .active_mesh_pose import active_document
from .motion_depth_overlap import Probe, inspect


class ActiveProbe:
    def __init__(self, document, files, animation, *, sparse=False):
        self.document, self.files, self.animation = document, files, animation
        self.remaining = 64_000_000
        self.sparse = sparse
        self.results = {}
        self.times = set()
        self.current_time = None
        self.current = None
        self.identities = None

    def pair(self, a, b, time):
        key = (min(a, b), max(a, b), time)
        if key in self.results:
            return deepcopy(self.results[key])
        if time not in self.times and len(self.times) >= 1025:
            raise ValueError('depth_overlap_frame_limit')
        if self.current_time != time:
            normalized, identities = active_document(self.document, self.animation, time)
            for name, identity in identities.items():
                if identity is not None:
                    normalized['skins'][0]['attachments'][name][name].setdefault('path', identity)
            # active_document freezes only the active mesh/deform. Preserve alpha
            # and reject unsupported remaining slot channels through normal Probe.
            tracks = {name: {k: deepcopy(v) for k, v in row.items() if k != 'attachment'}
                      for name, row in self.document['animations'][self.animation].get('slots', {}).items()}
            normalized['animations'][self.animation]['slots'] = {n: r for n, r in tracks.items() if r}
            self.current = Probe(normalized, self.files, self.animation, sparse=self.sparse,
                                 tiled=self.sparse, rendered_bounds=self.sparse)
            self.identities = identities
            self.current_time = time
            self.times.add(time)
        if a not in self.identities or b not in self.identities:
            raise ValueError('depth_overlap_slot_missing')
        if self.identities[a] is None or self.identities[b] is None:
            result = dict(status='sampled', overlap_pixels=0, roi=None)
        else:
            self.current.remaining = self.remaining
            try:
                result = self.current.pair(a, b, time)
            finally:
                self.remaining = self.current.remaining
        result = dict(result, active_attachments={n: self.identities[n] for n in (a, b)})
        self.results[key] = deepcopy(result)
        return result


def recheck(document, files, animation, depth, *, sparse=False):
    report, _ = inspect(document, files, animation, depth, sparse=sparse,
                        _probe=ActiveProbe(document, files, animation, sparse=sparse))
    report['target_overlap']['attachment_policy'] = 'active_attachment_uv_texture_and_deform'
    return report
