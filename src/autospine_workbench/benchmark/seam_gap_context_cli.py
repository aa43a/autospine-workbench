"""Read hash-verified preview bundles and export non-authoritative gap context."""
import argparse
import hashlib
import html
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.same_frame_seam import compare_frame
from ..targets.spine43.seam_raster import texture, mask
from ..targets.spine43.continuous_pose import world
from ..targets.spine43.seam_gap_context import classify


def load(report, directory, name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('gap_context_path')
    raw = (directory / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['files'][name]:
        raise ValueError('gap_context_file_hash')
    return raw


def analyze(before_report, after_report, before_dir, after_dir, *, observe=None):
    if before_report['schema'] != 'autospine.continuous-anchor-preview/v1' or after_report['schema'] != 'autospine.seam-increment-preview/v1':
        raise ValueError('gap_context_source_schema')
    if canonical_sha256(before_report) != after_report['source_anchor_sha256']:
        raise ValueError('gap_context_source_identity')
    before = json.loads(load(before_report, before_dir, 'skeleton.json'))
    after = json.loads(load(after_report, after_dir, 'skeleton.json'))
    qa = before_report['alpha_seam_qa']['after']; bounds = qa['boundaries']
    textures = {}
    for name in bounds:
        file = 'editor/images/' + name + '.png'
        raw = load(before_report, before_dir, file)
        if raw != load(after_report, after_dir, file):
            raise ValueError('gap_context_texture_changed')
        textures[name] = texture(raw)
    records = []
    for relation, expected in zip(qa['relations'], after_report['common_frame_comparison']['relations'], strict=True):
        a, b = relation['driver'], relation['follower']; frames = []
        if (a, b) != (expected['driver'], expected['follower']):
            raise ValueError('gap_context_relation_order')
        for tick in range(61):
            metrics, _ = compare_frame(before, after, relation, bounds, textures, tick / 30)
            if metrics != expected['frames'][tick]:
                raise ValueError('gap_context_comparison_replay')
            occupied = []
            for doc in (before, after):
                pose = world(doc, tick / 30); attachments = doc['skins'][0]['attachments']
                occupied.append([mask(attachments[n][n], pose[n], textures[n], metrics['rect']) >= 8 for n in (a, b)])
            # Same corridor as the original comparison, reconstructed from its exact pairs.
            from ..targets.spine43.alpha_seam import position
            from ..targets.spine43.seam_raster import corridor
            scan = None
            for doc in (before, after):
                pose = world(doc, tick / 30)
                pairs = [(position(bounds[a]['samples'][p['driver_sample']], pose[a]), position(bounds[b]['samples'][p['follower_sample']], pose[b])) for p in relation['pairs']]
                current = corridor(pairs, metrics['rect']); scan = current if scan is None else scan | current
            added = scan & (occupied[0][0] | occupied[0][1]) & ~(occupied[1][0] | occupied[1][1])
            counts, labels = classify(*occupied[1], added)
            if sum(counts.values()) != metrics['new_gap_pixels']:
                raise ValueError('gap_context_count_mismatch')
            if observe is not None:
                observe(a, b, tick, metrics['rect'], labels.copy(), [m.copy() for m in occupied[1]])
            frames.append(dict(time=tick / 30, new_gap_pixels=metrics['new_gap_pixels'], **counts))
        records.append(dict(driver=a, follower=b, frames=frames,
                            totals={key: sum(f[key] for f in frames) for key in frames[0] if key != 'time'}))
    return dict(schema='autospine.seam-gap-context/v1', profile='alpha8-opposite-rays4-v1',
                source_before_sha256=canonical_sha256(before_report), source_after_sha256=canonical_sha256(after_report),
                authority='none', production_authorized=False, status='needs_review',
                coverage='new_gap_pixel_samples_only', runtime_raster_status='not_evaluated', relations=records)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'before-dir', 'after-dir', 'output-dir'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    try:
        report = analyze(json.loads(args.before.read_text()), json.loads(args.after.read_text()), args.before_dir, args.after_dir)
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        print(json.dumps(dict(status='blocked', reason_code='gap_context_input_or_replay_failed', authority='none')))
        return 1
    digest = canonical_sha256(report); args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / (digest + '.json')
    target.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
    body = '<h1>新增空白支撑证据</h1><p>计数为跨帧像素样本，不是独立裂缝数量。单附件支撑不等于外轮廓变化已获证实；所有类别均未自动放行。</p>'
    for row in report['relations']:
        body += '<h2>' + html.escape(row['driver'] + ' → ' + row['follower']) + '</h2><pre>' + html.escape(json.dumps(row['totals'], indent=2)) + '</pre>'
    (args.output_dir / 'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{font:18px system-ui;max-width:1000px;margin:40px auto}pre{background:#eee;padding:20px}</style>' + body, encoding='utf-8')
    print(json.dumps(dict(artifact_sha256=digest, relations=[r['totals'] for r in report['relations']])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
