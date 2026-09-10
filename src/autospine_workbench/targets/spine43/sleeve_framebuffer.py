"""Validate the scope of official WebGL sleeve contact capture receipts."""
import math
from ...asset.planning.sleeve_motion_envelope import MOTIONS


def summarize(doc, contact):
    if (doc.get('schema') != 'autospine.sleeve-framebuffer/v1' or doc.get('authority') != 'none'
            or doc.get('production_authorized') is not False or doc.get('status') != 'needs_review'
            or doc.get('scope') != 'isolated_sleeve_native_pixel_contact_probes'
            or doc.get('runtime_package') != '@esotericsoftware/spine-webgl'
            or doc.get('runtime_version') != '4.3.13' or doc.get('export_target') != '4.3.26'):
        raise ValueError('sleeve_framebuffer_identity')
    probes = sum(len(r['samples']) for r in contact['interfaces'])
    if probes <= 0 or doc['info']['probe_count'] != probes:
        raise ValueError('sleeve_framebuffer_probes')
    names = {n for n, _ in MOTIONS}
    expected = {(n, i) for n in names for i in range(257)}
    actual = set(); count = failed = 0; minimum = 255; error = 0.
    for frame in doc['frames']:
        key = frame['animation'], frame['index']
        if key not in expected or key in actual or frame['time'] != frame['index']/128:
            raise ValueError('sleeve_framebuffer_frames')
        actual.add(key)
        for field in ('tested_samples', 'failed_samples', 'visible_pixels', 'min_alpha'):
            if type(frame[field]) is not int or frame[field] < 0:
                raise ValueError('sleeve_framebuffer_counts')
        if (frame['tested_samples'] != probes or frame['failed_samples'] > probes
                or frame['failed_samples'] != len(frame['failures']) or not frame['visible_pixels']
                or frame['min_alpha'] > 255 or bool(frame['failed_samples']) != (frame['min_alpha'] < 8)):
            raise ValueError('sleeve_framebuffer_counts')
        value = frame['max_error_px']
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= .001:
            raise ValueError('sleeve_framebuffer_pose')
        count += probes; failed += frame['failed_samples']; minimum = min(minimum, frame['min_alpha']); error = max(error, value)
    if actual != expected: raise ValueError('sleeve_framebuffer_frames')
    captures = {(c['animation'], c['index']) for c in doc['captures']}
    if not {(n, i) for n in names for i in (0, 64, 128, 192, 256)} <= captures:
        raise ValueError('sleeve_framebuffer_captures')
    return dict(frames=len(actual), tested_samples=count, failed_samples=failed, min_alpha=minimum,
        max_error_px=error, status='sampled_contacts_passed' if not failed else 'needs_review',
        overlap_status='not_evaluated', authority='none', production_authorized=False)
