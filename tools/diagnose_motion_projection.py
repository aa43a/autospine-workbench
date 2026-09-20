"""Export source-bound projection intervals and curves for a compiled motion job."""
import argparse
from html import escape
import json
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.targets.character43.projection_diagnostics import (
    bvh_series, kimodo_series, summarize)


def render(report):
    cards = []
    times = report['times']
    for row in report['records']:
        points = ' '.join(f'{(t-times[0])/(times[-1]-times[0])*800:.3f},{160-v*150:.3f}'
                          for t, v in zip(times, row['visibility']))
        intervals = ''.join('<li>'+escape(f"{i['reason']}: {i['start_time']:.3f}–{i['end_time']:.3f}s"
            f"（源帧 {i['start_frame']+1}–{i['end_frame']+1}）")+'</li>' for i in row['intervals'])
        cards.append(f'<section><h2>{escape(row["role"])}</h2>'
            f'<p>最低可见长度 {row["minimum_visibility"]:.1%}，源时间 {row["minimum_time"]:.3f}s；'
            f'参考首帧 {row["baseline_visibility"]:.1%}</p>'
            f'<svg viewBox="0 0 800 175"><path d="M0 130H800" stroke="#ffb452" stroke-dasharray="5 5"/>'
            f'<polyline points="{points}" stroke="#63d2ef" fill="none" stroke-width="2"/></svg>'
            f'<ul>{intervals or "<li>当前投影长度门槛通过</li>"}</ul></section>')
    return '<!doctype html><meta charset="utf-8"><title>源动作投影诊断</title>' + '''
<style>body{font:16px system-ui;background:#101923;color:#e7eff6;padding:24px;max-width:1100px;margin:auto}section{border:1px solid #435363;padding:16px;margin:14px 0}svg{width:100%;background:#182735}li{margin:8px}</style>
<h1>源动作投影诊断</h1><p>曲线：二维投影长度 / 三维骨段长度。横轴为整个动作时间；虚线为当前 20% 门槛。
接近零表示骨段朝向镜头，不能靠增大权重或放宽网格门槛恢复缺失视图。此诊断不会修改动画或自动采用新视角。</p>
<p>这些是离散源帧的异常区间，不证明区间之间或任意视角安全；参考首帧塌缩时，仅裁剪后续片段仍不能恢复该绑定参考。</p>''' + ''.join(cards)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('job_id')
    p.add_argument('output', type=Path)
    p.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = p.parse_args()
    if not args.job_id.startswith('motion-') or not args.job_id[7:].isalnum():
        p.error('invalid motion job')
    with urlopen('http://127.0.0.1:8918/api/motions/'+args.job_id, timeout=180) as response:
        job = json.load(response)
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(args.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    mapping = json.loads((bundle.path/'map.json').read_bytes())
    if bundle.source_kind == 'kimodo_npz':
        data = kimodo_series(bundle.raw_npz, bundle.kimodo_source, mapping)
    else:
        data = bvh_series(parse_bvh((bundle.path/'source.bvh').read_bytes()), mapping)
    report = summarize(*data)
    report.update(source_job_id=args.job_id, source_sha256=job['source_sha256'],
                  motion_identity=identity, basis=mapping['basis'])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'index.html').write_text(render(report), encoding='utf-8')
    print(json.dumps([dict(role=r['role'], min=r['minimum_visibility'], time=r['minimum_time'],
                          passed=r['passed']) for r in report['records']]))


if __name__ == '__main__':
    main()
