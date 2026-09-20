"""Exact decoded-PNG comparison of complete, same-environment official captures."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image

from ...safe_input_files import read_real_file

PROFILE = 'official-capture-decoded-rgba-equivalence-v1'


def _load(root):
    raw = read_real_file(root/'report.json', 64 << 20, 'capture report')
    report = json.loads(raw)
    if (report.get('schema') != 'autospine.character-framebuffer/v1' or report.get('passed') is not True
            or report.get('authority') != 'none' or report.get('production_authorized') is not False):
        raise ValueError('equivalence_capture_not_passed')
    frames = {(r['animation'], r['index']): r for r in report['results']}
    images = {(r['animation'], r['index']): r for r in report['screenshots']}
    if (not frames or len(frames) != len(report['results']) or len(images) != len(report['screenshots'])
            or frames.keys() != images.keys()):
        raise ValueError('equivalence_incomplete_frame_inventory')
    return report, frames, images, sha256(raw).hexdigest()


def _image(root, row, size):
    name = row['file']; path = PurePosixPath(name)
    if path.is_absolute() or '\\' in name or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('equivalence_image_path')
    raw = read_real_file(root/path, 64 << 20, 'capture image')
    if sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('equivalence_image_identity')
    with Image.open(BytesIO(raw)) as img:
        if img.size != size or img.format != 'PNG':
            raise ValueError('equivalence_image_dimensions')
        return np.asarray(img.convert('RGBA'), dtype=np.int16)


def compare(before, after):
    roots = [Path(before), Path(after)]
    a, b = [_load(root) for root in roots]
    fields = ['runtime_package', 'runtime_version', 'runtime_sha256', 'harness_sha256',
              'tool_sha256', 'draw_order_reader_sha256', 'reference_reader_sha256', 'browser_sha256', 'profile']
    if any(not a[0].get(k) or a[0][k] != b[0].get(k) for k in fields):
        raise ValueError('equivalence_environment_mismatch')
    info = [{k:v for k,v in r[0]['info'].items() if k != 'slots'} for r in (a,b)]
    if info[0] != info[1] or a[1].keys() != b[1].keys():
        raise ValueError('equivalence_camera_or_frames_mismatch')
    size = (info[0]['width'], info[0]['height'])
    if not all(type(n) is int and 0 < n <= 4096 for n in size):
        raise ValueError('equivalence_framebuffer_bound')
    rows = []
    for key in sorted(a[1]):
        if a[1][key]['time'] != b[1][key]['time']:
            raise ValueError('equivalence_time_mismatch')
        first = _image(roots[0], a[2][key], size); second = _image(roots[1], b[2][key], size)
        delta = np.abs(first-second)
        rows.append(dict(animation=key[0], index=key[1], time=a[1][key]['time'],
                         changed_pixels=int(np.any(delta, axis=2).sum()), max_channel_delta=int(delta.max())))
    return dict(profile=PROFILE, passed=all(r['changed_pixels']==0 for r in rows),
                authority='none', selected=False, source_report_sha256=[a[3],b[3]],
                source_bundle_sha256=[a[0]['bundle_sha256'],b[0]['bundle_sha256']], frames=rows,
                scope='decoded_png_rgba_at_captured_times_not_continuous_time_or_visual_acceptance')
