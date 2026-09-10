"""Source-bound overlap diagnostics for ordinary workflows, without GPU admission."""
import math
from .storage_io import read_document
from ..resolved_project import canonical_sha256
from ..asset.planning.sleeve_motion_envelope import MOTIONS


def _candidate(value):
    return (value.get('authority') == 'none' and value.get('production_authorized') is False
            and value.get('framebuffer_status') == 'not_evaluated')


def _count(value):
    return type(value) is int and value >= 0


def _track(track):
    counts = [track.get(k) for k in ('frames', 'frames_with_increased_overlap',
              'tested_pair_frames', 'frames_with_increased_dual_alpha8')]
    if (not all(_count(v) for v in counts) or counts[0] != 257
            or max(counts[1], counts[3]) > counts[0] or counts[3] > counts[2]):
        raise ValueError('sleeve_overlap_counts')
    peak = track.get('visible_peak')
    if not counts[3]:
        if peak is not None: raise ValueError('sleeve_overlap_peak')
        return 0
    if not isinstance(peak, dict): raise ValueError('sleeve_overlap_peak')
    values = [peak.get(k) for k in ('excess_pair_pixels', 'setup_pair_pixels', 'tested_pixels', 'dual_alpha8_pixels')]
    time, alpha = peak.get('time'), peak.get('max_min_alpha')
    pair = peak.get('triangles')
    if (not all(_count(v) for v in values) or values[0] <= 0
            or values[0] != values[3]-values[1] or values[3] > values[2]
            or type(time) not in (int, float) or not math.isfinite(time) or not 0 <= time <= 2
            or type(alpha) not in (int, float) or not math.isfinite(alpha) or not 8 <= alpha <= 255
            or not isinstance(pair, list) or len(pair) != 2 or not all(_count(v) for v in pair) or pair[0] == pair[1]
            or peak.get('scope') != 'pair_bbox_native_centers'):
        raise ValueError('sleeve_overlap_peak')
    return values[0]


def summaries(root, project, export):
    paths = list((root/'overlap'/project).glob('*.json'))
    if len(paths) != 1: raise ValueError('sleeve_overlap_report_inventory')
    doc = read_document(paths[0])
    if (paths[0].stem != canonical_sha256(doc) or doc.get('purpose') != 'sleeve_overlap_diagnostic'
            or doc.get('project_id') != project or doc.get('source_report_sha256') != canonical_sha256(export)
            or not _candidate(doc)):
        raise ValueError('sleeve_overlap_report_source')
    expected = {(r['layer_id'], r['component_id']): r for r in export['records'] if r['status'] == 'candidate_exported'}
    rows = {}
    for row in doc['records']:
        key = row['layer_id'], row['component_id']
        if key in rows or key not in expected or row['asset_sha256'] != expected[key]['files']:
            raise ValueError('sleeve_overlap_region_inventory')
        if (not _candidate(row) or row.get('status') != 'diagnostic_only'
                or row.get('profile') != 'pairwise-triangle-overlap-v2'
                or row.get('texture_visibility') != 'native_centers_all_intersecting_pairs'):
            raise ValueError('sleeve_overlap_status')
        tracks = row['tracks']
        if len(tracks) != len(MOTIONS) or {t['animation'] for t in tracks} != {n for n, _ in MOTIONS}:
            raise ValueError('sleeve_overlap_motion_inventory')
        peaks = [_track(t) for t in tracks]
        rows[key] = dict(status='diagnostic_only', frames=sum(t['frames'] for t in tracks),
            tested_pair_frames=sum(t['tested_pair_frames'] for t in tracks),
            affected_frames=sum(t['frames_with_increased_dual_alpha8'] for t in tracks),
            peak_excess_pair_pixels=max(peaks), report_sha256=canonical_sha256(doc),
            framebuffer_status='not_evaluated')
    if rows.keys() != expected.keys(): raise ValueError('sleeve_overlap_region_inventory')
    return rows
