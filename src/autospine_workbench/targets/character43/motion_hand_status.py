"""Supplemental source hand visibility, bound to a candidate and clipped timeline."""
import json
from html import escape
from ...motion_validation import motion_ir_sha256
from .motion_clip import boundaries,clip_motion
from .oblique_target import prepare
from .source_palm_plane import extract


def summarize(rows,bounds=None):
    origin=bounds[0]/1e6 if bounds else 0
    chosen=[r for r in rows if bounds is None or bounds[0]-1e-3<=r['time']*1e6<=bounds[1]+1e-3]
    result=[]
    for side in ('left','right'):
        intervals=[];active=None
        for row in chosen:
            value=row['hands'][side]['projected_area_fraction'];t=row['time']-origin
            if value<.2:
                if active is None:active=dict(start=t,end=t,samples=0,minimum_fraction=value);intervals.append(active)
                active.update(end=t,samples=active['samples']+1,minimum_fraction=min(active['minimum_fraction'],value))
            else:active=None
        result.append(dict(side=side,sampled_count=len(chosen),intervals=intervals))
    return result


def build(files,artifact,bundle,request):
    identity=request['motion_identity'];manifest=json.loads(files['character-manifest.json'])
    if manifest['source_motion_bundle_sha256']!=identity['bundle_sha256']:raise ValueError('hand_status_source_mismatch')
    motion=bundle.motion
    from .camera_track import PROFILE as CAMERA_PROFILE
    camera_keys=(request['projection']['keys'] if (request.get('projection') or {}).get('profile')==CAMERA_PROFILE else None)
    if camera_keys is not None:
        from ...automation.motion_camera_pose import prepare as prepare_camera
        motion,_,_=prepare_camera(bundle,camera_keys,sampling_profile=request['projection'].get('sampling_profile'))
    elif request.get('projection') is not None:motion,_=prepare(bundle,request['projection'])
    ticks=[k['tick'] for k in next(t for t in motion['tracks'] if t['property']=='rotation')['keys']]
    bounds=boundaries(request.get('clip'),ticks)
    if motion_ir_sha256(clip_motion(motion,bounds))!=motion_ir_sha256(json.loads(files['motion-ir.json'])):
        raise ValueError('hand_status_motion_mismatch')
    result=dict(profile='source-hand-visibility-status-v1',artifact_sha256=artifact,motion_identity=identity,
        authority='none',selected=False,animation_modified=False,clip=request.get('clip'),records=[],
        scope='source_knuckle_plane_not_target_hand_texture_or_acceptance',threshold=.2)
    options=dict(camera_keys=camera_keys,sampling_profile=request['projection'].get('sampling_profile')) if camera_keys is not None else {}
    try:observation=extract(bundle,yaw=(request.get('projection') or {}).get('yaw_degrees',0),**options)
    except ValueError as exc:
        return dict(result,status='unavailable',reason=str(exc))
    return dict(result,status='observed',records=summarize(observation['rows'],bounds),
                observation_profile=observation['profile'],limitations=observation['limitations'])


def render(report):
    rows=''
    for record in report['records']:
        for interval in record['intervals']:
            rows+=f'<tr><td>{"左手" if record["side"]=="left" else "右手"}</td><td>{interval["start"]:.3f}–{interval["end"]:.3f} s</td><td>{interval["samples"]}</td><td>{interval["minimum_fraction"]:.1%}</td></tr>'
    body=('<table><tr><th>部位</th><th>候选时间</th><th>源采样数</th><th>最小面积比例</th></tr>'+rows+'</table>') if rows else '<p>没有此类观测区间，或来源暂不支持；这不代表目标贴图正确。</p>'
    return ('<!doctype html><meta charset="utf-8"><title>手部侧向区间</title><style>body{background:#15232e;color:white;font:18px sans-serif;margin:30px}td,th{padding:12px}a{color:#7ce4ef}</style><h1>手部侧向区间</h1><p>源掌面投影面积低于 20% 的连续采样；区间时间已对齐当前动作片段。不是绑定错误判定，不修改动画。</p>'+body+'<p>'+escape(report.get('reason','掌心/手背尚未与目标贴图注册，需结合实际画面判断素材表达。'))+'</p><a href="player.html">播放候选</a> · <a href="hand-status.json">完整证据</a>').encode('utf-8')
