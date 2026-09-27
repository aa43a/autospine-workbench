"""Compare verified source projections without selecting or accepting a target view."""
import argparse
import json
from pathlib import Path

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.oblique_motion import project
from autospine_workbench.targets.character43.lower_limb_projection import view_summary


from autospine_workbench.targets.character43.source_view_scan import scan


def run(state, request_path, output):
    request = json.loads(request_path.read_bytes())
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
    vectors, _, _ = extract(bundle)
    from autospine_workbench.targets.character43.torso_projection_source import anchors, reference_shapes
    front, ticks = anchors(bundle, 0)
    candidates = scan(vectors, range(-90, 91, 5))
    for candidate in candidates:
        candidate['knees']=view_summary(vectors,candidate['yaw_degrees'])
        frames = [[project(point, candidate['yaw_degrees']) for point in frame] for frame in front]
        torso = reference_shapes(frames, [tick/1e6 for tick in ticks], front[0])
        rows = torso['records']
        candidate['torso'] = dict(source_supported=all(not row['reasons'] for row in rows),
                                 minimum_width_ratio=min(row['transverse'] for row in rows),
                                 maximum_width_ratio=max(row['transverse'] for row in rows),
                                 reasons=sorted({reason for row in rows for reason in row['reasons']}),
                                 limits=torso['limits'])
    report = dict(schema='autospine.source-view-scan/v1', motion_identity=identity,
                  request_sha256=canonical_sha256(request),
                  spatial_vectors_sha256=canonical_sha256(vectors),
                  candidates=candidates, authority='none', selected=False,
                  scope='source_samples_only_not_target_geometry_contact_or_visual_acceptance',
                  limitations=['view_change_requires_matching_character_artwork_and_occlusion',
                               'adjacent_angle_is_not_angular_velocity_or_interpolation_validation'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    with output.with_suffix('.html').open('x',encoding='utf-8') as stream:
        stream.write(render(report))


def render(report):
    rows=[]
    for r in report['candidates']:
        k=r['knees'];loss=k['maximum_hidden_bend_deg']
        value='未测' if loss is None else f'{loss:.2f}°'
        rows.append(f'<tr><td>{r["yaw_degrees"]}°</td><td>{value}</td>'
            f'<td>{k["samples_losing_30_degrees"]}/{k["sample_count"]}</td>'
            f'<td>{"通过" if r["torso"]["source_supported"] else "超出支持范围"}</td></tr>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>来源视角与膝部表现</title>
<style>body{background:#15212c;color:#e8eff6;font:16px system-ui;margin:24px}table{border-collapse:collapse}td,th{padding:8px 20px;border:1px solid #4b6070}p{max-width:1000px;line-height:1.6}</style>
<h1>来源视角与膝部表现</h1><p>同一完整动作的来源骨轴比较。膝部更清楚不代表角色轮廓、接触、遮挡或正侧面素材匹配。30°仅用于定位深度损失，不是视觉采用门槛。没有自动选择或替换候选。</p>
<table><tr><th>视角</th><th>最大隐藏弯曲</th><th>损失至少30°的左右腿采样</th><th>来源躯干投影检查</th></tr>'''+''.join(rows)+'</table></html>'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('state', 'request', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.state, args.request, args.output)
