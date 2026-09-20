"""Read-only, exact-source projection diagnostics for the motion center."""
from hashlib import sha256
from html import escape
import json

from ..bvh_parser import parse_bvh
from ..motion_bundle_reader import VerifiedMotionBundleReader
from ..safe_input_files import read_real_file
from ..targets.character43.projection_diagnostics import bvh_series, kimodo_series, summarize
from .pipeline_run import PipelineRunError


def inspect(manager, job_id):
    job = manager.get(job_id)
    if job.get('kind') == 'adapt' or job['status'] != 'succeeded' or job['result'].get('motion_status') != 'compiled':
        raise PipelineRunError('motion_projection_source_unavailable')
    raw = read_real_file(manager.folder(job_id)/('source.'+job['format']), 64 << 20, 'motion source')
    if sha256(raw).hexdigest() != job['source_sha256']:
        raise PipelineRunError('motion_source_changed')
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(manager.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    mapping = json.loads((bundle.path/'map.json').read_bytes())
    data = (kimodo_series(bundle.raw_npz, bundle.kimodo_source, mapping) if bundle.source_kind == 'kimodo_npz'
            else bvh_series(parse_bvh((bundle.path/'source.bvh').read_bytes()), mapping))
    report = summarize(*data)
    report.update(source_job_id=job_id, source_sha256=job['source_sha256'], motion_identity=identity,
                  basis=mapping['basis'], source_name=job['name'], view=job['view'])
    return report


def render(report):
    cards = []
    times = report['times']
    reasons = {'projected_segment_below_20_percent': '投影长度不足三维骨段的 20%',
               'relative_length_outside_half_to_one_and_half': '相对首帧长度超出 0.5–1.5 倍'}
    for row in report['records']:
        points = ' '.join(f'{(t-times[0])/(times[-1]-times[0])*800:.3f},{160-v*150:.3f}'
                          for t, v in zip(times, row['visibility']))
        intervals = ''.join('<li>'+escape(f"{reasons[i['reason']]}: {i['start_time']:.3f}–{i['end_time']:.3f}s"
            f"（源帧 {i['start_frame']+1}–{i['end_frame']+1}）")+'</li>' for i in row['intervals'])
        cards.append(f'<section><h2>{escape(row["role"])}</h2>'
            f'<p>最低可见长度 {row["minimum_visibility"]:.1%}，源时间 {row["minimum_time"]:.3f}s；'
            f'参考首帧 {row["baseline_visibility"]:.1%}</p>'
            f'<svg viewBox="0 0 800 175"><path d="M0 130H800" stroke="#ffb452" stroke-dasharray="5 5"/>'
            f'<polyline points="{points}" stroke="#63d2ef" fill="none" stroke-width="2"/></svg>'
            f'<ul>{intervals or "<li>当前投影长度门槛通过</li>"}</ul></section>')
    name = escape(report.get('source_name', ''))
    view = escape({'front': '正面', 'side': '侧面'}.get(report.get('view'), '已记录的来源视角'))
    return ('<!doctype html><meta charset="utf-8"><title>源动作投影诊断</title>' + '''
<style>body{font:16px system-ui;background:#101923;color:#e7eff6;padding:24px;max-width:1100px;margin:auto}section{border:1px solid #435363;padding:16px;margin:14px 0}svg{width:100%;background:#182735}li{margin:8px}a{color:#63d2ef}</style>
<h1>源动作投影诊断</h1><p>曲线：二维投影长度 / 三维骨段长度。横轴为整个动作时间；虚线为当前 20% 门槛。
接近零表示骨段朝向镜头，不能靠增大权重或放宽网格门槛恢复缺失视图。此诊断不会修改动画或自动采用新视角。</p>
<p>这些是离散源帧的异常区间，不证明区间之间或任意视角安全；参考首帧塌缩时，仅裁剪后续片段仍不能恢复该绑定参考。</p>'''
        + '<p>'+name+' · '+view+'</p>' + ''.join(cards)).encode('utf-8')
