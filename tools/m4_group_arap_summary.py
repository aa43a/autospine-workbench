"""Summarize actual full-clip capture without upgrading candidate authority."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    root = parser.parse_args().folder
    probe = json.loads((root/'probe.json').read_bytes())
    runtime = json.loads((root/'candidate/runtime/report.json').read_bytes())
    geometry = json.loads((root/'candidate/runtime/deformation.json').read_bytes())
    receipt = json.loads((root/'candidate/report.json').read_bytes())
    if runtime['bundle_sha256'] != receipt['candidate_bundle_sha256']:
        raise ValueError('arap_summary_runtime_identity')
    times = sorted({r['time'] for r in probe['records']})
    failures = [r for r in geometry['records'] if not r['passed']]
    if geometry['passed'] or not failures:
        raise ValueError('failure_review_requires_failed_geometry')
    summary = dict(authority='none', selected=False, candidate=receipt['candidate_bundle_sha256'],
        solved_key_count=len(times), runtime_sample_count=len(runtime['results']),
        runtime_numeric_passed=runtime['passed'], geometry_passed=geometry['passed'], failures=failures,
        visual_status='not_accepted',
        evidence_hashes={name: sha256((root/name).read_bytes()).hexdigest() for name in
            ('probe.json', 'candidate/runtime/report.json', 'candidate/runtime/deformation.json')})
    (root/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    rows = ''.join(f'<tr><td>{escape(r["slot"])}</td><td>{r["failing_frame_count"]}</td>'
        f'<td>{r["inversion_samples"]}</td><td>{r["first_failure"]["time"]:.6f}</td></tr>' for r in failures)
    images = ''.join(f'<figure><figcaption>Runtime 采样编号 {p.stem.rsplit("-",1)[1]}</figcaption>'
        f'<img src="candidate/runtime/frames/{escape(p.name)}"></figure>'
        for p in sorted((root/'candidate/runtime/frames').glob('*.png')))
    html = '<!doctype html><meta charset="utf-8"><title>分部位投影整段检查</title>'
    html += '<style>body{background:#101923;color:white;font:16px system-ui;margin:24px}td,th{padding:10px;border:1px solid #567}figure{display:inline-block;width:30%;vertical-align:top;margin:1%}img{width:100%}</style>'
    html += f'<h1>整段检查：候选未采用</h1><p>{len(times)} 个解算关键帧，{len(runtime["results"])} 个 Runtime 采样。数值一致性与几何通过分别记录。</p>'
    html += '<p>膝部轮廓及整体姿态仍不自然；本页是失败定位，不是验收邀请。停止扩大局部位移预算和放宽门禁。</p>'
    html += '<table><tr><th>区域</th><th>失败帧数</th><th>翻转采样数</th><th>首次失败秒</th></tr>'+rows+'</table>'+images
    (root/'review.html').write_text(html, encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('failures','evidence_hashes')}))


if __name__ == '__main__': main()
