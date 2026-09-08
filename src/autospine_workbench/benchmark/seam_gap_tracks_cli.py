"""Replay gap context and publish immutable non-authoritative component tracks."""
import argparse
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.seam_gap_tracks import components, associate
from .seam_gap_context_cli import analyze
from .seam_gap_tracks_view import render


def compile_report(before, after, before_dir, after_dir, *, visual_sink=None):
    import numpy as np
    from PIL import Image
    observations = {}; visuals = {}

    def observe(a, b, tick, rect, labels, masks):
        key = (a, b)
        observations.setdefault(key, []).append(components(labels, rect, tick))
        rgb = np.full((*labels.shape, 3), 245, dtype=np.uint8)
        rgb[masks[0]] = [99, 175, 232]; rgb[masks[1]] = [112, 196, 139]
        rgb[masks[0] & masks[1]] = [110, 95, 190]; rgb[labels > 0] = [230, 45, 45]
        output = BytesIO(); Image.fromarray(rgb).save(output, format='PNG')
        visuals.setdefault(key, []).append(dict(rect=rect, image='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()))

    context = analyze(before, after, before_dir, after_dir, observe=observe)
    rows = []
    for relation in context['relations']:
        key = (relation['driver'], relation['follower']); row = associate(observations[key])
        if row['pixel_samples'] != relation['totals']['new_gap_pixels']:
            raise ValueError('gap_track_pixel_conservation')
        row.update(driver=key[0], follower=key[1]); rows.append(row)
    report = dict(schema='autospine.seam-gap-tracks/v1', profile='eight-connected-mutual-unique-world3-v1',
                  source_context_sha256=canonical_sha256(context), source_before_sha256=canonical_sha256(before),
                  source_after_sha256=canonical_sha256(after), authority='none', production_authorized=False,
                  status='needs_review', coordinate_system='world_xy_y_up_pixel_centers', fps=30, sample_count=61,
                  coverage='new_gap_pixel_samples_only', runtime_raster_status='not_evaluated', relations=rows)
    if visual_sink is not None:
        visual_sink.extend(visuals.values())
    return report, render(report, list(visuals.values()))


def read_tracks(saved, before, after, before_dir, after_dir):
    """Exact replay of this diagnostic, without claiming an upstream compile replay."""
    if saved.get('schema') != 'autospine.seam-gap-tracks/v1':
        raise ValueError('gap_tracks_reader_schema')
    expected, _ = compile_report(before, after, before_dir, after_dir)
    if canonical_sha256(saved) != canonical_sha256(expected):
        raise ValueError('gap_tracks_reader_mismatch')
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'before-dir', 'after-dir', 'output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    try:
        report, page = compile_report(json.loads(args.before.read_text()), json.loads(args.after.read_text()), args.before_dir, args.after_dir)
        digest = canonical_sha256(report); args.output_dir.mkdir(parents=True, exist_ok=True)
        target = args.output_dir / (digest+'.json')
        if target.exists() and canonical_sha256(json.loads(target.read_text())) != digest:
            raise ValueError('gap_track_existing_corrupt')
        target.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n', encoding='utf-8')
        (args.output_dir/'index.html').write_text(page, encoding='utf-8')
        print(json.dumps(dict(artifact_sha256=digest, page_sha256=hashlib.sha256((args.output_dir/'index.html').read_bytes()).hexdigest(),
                              relations=[dict(driver=r['driver'], tracks=len(r['tracks']), events=len(r['association_events']), pixels=r['pixel_samples']) for r in report['relations']])));
        return 0
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        print(json.dumps(dict(status='blocked', reason_code='gap_tracks_input_or_replay_failed', authority='none'))); return 1


if __name__ == '__main__':
    raise SystemExit(main())
