"""Present an audited cloth diagnostic with full-motion framing and failures."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.storage_io import canonical_bytes
from m4_regional_cloth_runtime_audit import audit
from m4_runtime_batch_player import viewport


def run(source,experiment,parent,root):
    checked=audit(source,experiment,parent,root)
    if not checked['complete']:raise ValueError('cloth_player_complete_runtime_required')
    manifest=json.loads((root/'report.json').read_bytes())
    diagnostic=json.loads((experiment/'report.json').read_bytes())
    first=manifest['rows'][0];folder=root/first['folder']
    scene_path=folder/'runtime/player-assets/scene.json'
    scene=json.loads(scene_path.read_bytes())
    if (scene['artifact_sha256']!=first['candidate_bundle_sha256'] or
        sha256(canonical_bytes(scene['skeleton'])).hexdigest()!=manifest['skeleton_sha256']):
        raise ValueError('cloth_player_scene_identity')
    infos=[json.loads((root/r['folder']/'runtime/report.json').read_bytes())['info'] for r in manifest['rows']]
    bounds=viewport(infos);scene['info'].update(bounds);scene_path.write_bytes(canonical_bytes(scene))
    failed=[r for r in diagnostic['frames'] if r['uncovered']]
    if not failed:raise ValueError('cloth_player_expected_diagnostic_failures')
    link=f"{first['folder']}/runtime/player.html"
    report=dict(coverage=checked['coverage'],viewport=bounds,player=link,
        scene_sha256=sha256(scene_path.read_bytes()).hexdigest(),skeleton_sha256=manifest['skeleton_sha256'],
        coverage_failed_times=len(failed),coverage_checked_times=len(diagnostic['frames']),
        diagnostic_report_sha256=sha256((experiment/'report.json').read_bytes()).hexdigest(),
        authority='none',selected=False,production_authorized=False,
        scope='audited_diagnostic_player_not_visual_acceptance')
    (root/'player-report.json').write_bytes(canonical_bytes(report))
    times=sorted({failed[0]['time'],.8,.9,.9641929343342781,1.,failed[-1]['time']})
    links=' '.join(f'<a target="motion" href="{link}?time={t:.9f}">{t:.3f} 秒</a>' for t in times)
    html=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>Alice 下蹲 · 裙片连续修复诊断</title>
<style>body{{background:#101923;color:#e6edf4;font:16px system-ui;margin:20px}}a{{color:#78d8ff;margin-right:16px}}
iframe{{width:100%;height:78vh;border:1px solid #425568}}p{{max-width:1100px;line-height:1.6}}
.warning{{color:#ffd184}}</style>
<h1>Alice 下蹲 · 裙片连续修复诊断</h1>
<p class="warning">候选未采用：−55° 独立实验视角。保留原绑定与纹理；本页不代表三角色固定基线已通过。</p>
<p>官方 Runtime 已核对 {checked['coverage']['frames']:,} 个不重复时刻。
材质覆盖检查仍有 {len(failed)} / {len(diagnostic['frames'])} 个时刻失败。
数值播放通过不代表裂缝、遮挡或动作外观通过。</p>
<p>跳到重点时刻：{links}</p>
<iframe name="motion" title="动作与时间轴" src="{link}?time=0.9"></iframe>
<p><a href="{link}" target="_blank">独立打开播放器</a><a href="player-report.json">播放与验证记录</a>
<a href="report.json">完整 Runtime 记录</a></p></html>'''
    (root/'index.html').write_text(html,encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','experiment','parent','root'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.parent,a.root)
