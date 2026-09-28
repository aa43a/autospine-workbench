"""Freeze six M5 candidates into one official-player stage-review page.

Usage: python tools/build_m5_review.py --input tmp/m5-joint/review-map.json
The generated page only writes local, version-bound visual review drafts.
It never imports M4 acceptance or changes server-side acceptance records.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

CHARACTERS = {'alice': '爱丽丝', 'huiye': '辉夜', 'hongmeiling': '红美铃'}
MOTIONS = {'breathing': '呼吸', 'wave': '挥手'}
JOB = re.compile(r'^motion-[a-f0-9]{32}$')
SHA = re.compile(r'^[a-f0-9]{64}$')


def freeze(mapping, state_root, acceptance=None):
    if mapping.get('schema') != 'autospine.m5-review-map/v1':
        raise ValueError('m5_review_mapping_schema')
    base = mapping.get('base_url', 'http://127.0.0.1:8918').rstrip('/')
    url = urlsplit(base)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost')
            or url.path or url.query or url.fragment or url.username or url.password):
        raise ValueError('m5_review_local_base_url_required')
    expected = {(c, m) for c in CHARACTERS for m in MOTIONS}
    seen, samples, jobs, projects = set(), [], set(), {}
    for row in mapping.get('samples', []):
        key = (row.get('character'), row.get('motion'))
        if key not in expected or key in seen or not JOB.fullmatch(row.get('job_id', '')):
            raise ValueError('m5_review_sample_identity')
        seen.add(key)
        if row['job_id'] in jobs:
            raise ValueError('m5_review_repeated_job')
        jobs.add(row['job_id'])
        folder = Path(state_root)/'jobs/motion-intake-v1'/row['job_id']
        job = json.loads((folder/'result.json').read_bytes())
        request = json.loads((folder/'request.json').read_bytes())
        result = job.get('result', {})
        artifact = result.get('artifact_sha256', '')
        execution = request.get('joint_execution', {})
        project = job.get('project_id')
        if (not project or request.get('project_id') != project
                or row.get('project_id', project) != project
                or key[0] in projects and projects[key[0]] != project
                or any(name != key[0] and value == project for name, value in projects.items())):
            raise ValueError('m5_review_character_project_mismatch')
        projects[key[0]] = project
        if (job.get('job_id') != row['job_id'] or job.get('status') != 'succeeded'
                or not result.get('joint_animation_profile') or not execution
                or not SHA.fullmatch(artifact)
                or result.get('joint_parent_job_id') != execution.get('parent_job_id')
                or result.get('joint_parent_artifact_sha256') != execution.get('parent_artifact_sha256')):
            raise ValueError('m5_review_joint_result_required')
        if row.get('artifact_sha256') and row['artifact_sha256'] != artifact:
            raise ValueError('m5_review_artifact_changed')
        config = execution.get('config', {})
        runtime, summary = result.get('runtime', {}), result.get('joint_summary', {})
        if result.get('geometry_passed') is not True or runtime.get('geometry_status') != 'passed':
            raise ValueError('m5_review_runtime_geometry_required')
        samples.append(dict(character=key[0], character_label=CHARACTERS[key[0]],
            motion=key[1], motion_label=MOTIONS[key[1]], job_id=job['job_id'],
            project_id=project,
            artifact_sha256=artifact, parent_job_id=execution['parent_job_id'],
            parent_artifact_sha256=execution['parent_artifact_sha256'],
            duration=execution.get('duration'), geometry_passed=result.get('geometry_passed'),
            runtime=dict(status=runtime.get('status'), geometry_status=runtime.get('geometry_status'), frames=runtime.get('frames')),
            face=summary.get('face', {}), secondary=summary.get('secondary', {}),
            preservation=summary.get('preservation', {}),
            loop=dict(**{k: summary.get('loop', {}).get(k) for k in ('requested', 'status', 'measured_passed', 'visual_status')},
                      source_body={'loop_ready': summary.get('loop', {}).get('source_body', {}).get('loop_ready')},
                      added_effects={'passed': summary.get('loop', {}).get('added_effects', {}).get('passed')}),
            enabled={k: bool(config.get(k, {}).get('enabled')) for k in ('face', 'hair', 'cloth')},
            mouth_template_enabled=bool(config.get('face', {}).get('mouth', {}).get('template_enabled')),
            mouth_uploaded=bool(config.get('face', {}).get('mouth', {}).get('template_image')),
            contact_status=result.get('contact_status'),
            depth_order_status=result.get('depth_order_status'),
            issues=result.get('issues', []), inherited_issue_context=result.get('inherited_issue_context', []),
            visual_status='not_evaluated', authority='none'))
    if seen != expected:
        raise ValueError('m5_review_exact_six_samples_required')
    if acceptance is not None:
        apply_acceptance(samples, acceptance, state_root)
    return dict(schema='autospine.m5-review-snapshot/v1', generated_at=datetime.now(timezone.utc).isoformat(),
                base_url=base, characters=CHARACTERS, motions=MOTIONS, samples=samples,
                visual_status='server_stage_records_verified' if acceptance is not None else 'not_evaluated', authority='none')


def apply_acceptance(samples, rows, state_root):
    if not isinstance(rows, list) or len(rows) != len(samples):
        raise ValueError('m5_review_acceptance_cohort_mismatch')
    by_job = {row.get('job_id'): row for row in rows}
    if set(by_job) != {sample['job_id'] for sample in samples}:
        raise ValueError('m5_review_acceptance_cohort_mismatch')
    for sample in samples:
        row = by_job[sample['job_id']]
        current = row.get('current') or {}
        readiness = row.get('readiness') or {}
        digest = sha256(json.dumps(readiness, ensure_ascii=False, allow_nan=False,
                                  sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (row.get('character') != sample['character'] or row.get('motion') != sample['motion']
                or row.get('current_applies') is not True or row.get('evidence_match') != 'exact'
                or current.get('schema') != 'autospine.motion-stage-review/v1'
                or current.get('job_id') != sample['job_id']
                or any(value != sample['artifact_sha256'] for value in
                       [row.get('artifact_sha256'), current.get('artifact_sha256'), readiness.get('artifact_sha256')])
                or row.get('evidence_sha256') != digest or current.get('evidence_sha256') != digest
                or current.get('revision') != row.get('revision')
                or current.get('decision') not in {'accepted', 'accepted_with_exceptions', 'rejected', 'revoked'}):
            raise ValueError('m5_review_acceptance_evidence_mismatch')
        folder = Path(state_root)/'jobs/motion-intake-v1'/sample['job_id']/'stage-reviews'
        paths = sorted(folder.glob('review-*.json'))
        if (not paths or paths[-1].name != f"review-{row['revision']:04d}.json"
                or json.loads(paths[-1].read_bytes()) != current):
            raise ValueError('m5_review_acceptance_server_record_mismatch')
        sample['server_review'] = {k: current.get(k) for k in
            ('decision', 'revision', 'evidence_sha256', 'created_at', 'notes', 'readiness_status')}
        sample['server_review']['source'] = 'verified_server_stage_review_snapshot'
        sample['visual_status'] = current['decision']


def render(snapshot):
    data = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    return HTML.replace('__SNAPSHOT__', data)


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>M5 联合动画集中验收</title>
<style>
:root{color-scheme:dark;font-family:system-ui,"Microsoft YaHei",sans-serif;color:#dcebf5;background:#0d1720}*{box-sizing:border-box}body{margin:0}header{padding:20px 24px;border-bottom:1px solid #355063;background:#142532}h1{font-size:24px;margin:0 0 8px}p{line-height:1.6;margin:8px 0}a{color:#86d9ff;text-underline-offset:3px}button,select,textarea{font:inherit;color:inherit;background:#1b3346;border:1px solid #587789;border-radius:6px;min-height:44px;padding:9px 12px}button{cursor:pointer}button:focus-visible,a:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #7bd9ff;outline-offset:3px}label{display:flex;gap:10px;align-items:center}main{padding:18px 24px;max-width:1900px;margin:auto}.toolbar{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin-bottom:14px}.overview{display:flex;flex-wrap:wrap;gap:8px}.overview span{padding:7px 12px;background:#203a4d;border-radius:6px}.layout{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(330px,1fr);gap:20px;align-items:start}iframe{display:block;width:100%;height:78vh;min-height:580px;border:1px solid #456477;border-radius:8px;background:#101b25}.card{padding:15px;border:1px solid #3b586c;border-radius:8px;background:#142532;margin-bottom:14px}h2{font-size:18px;margin:0 0 10px}h3{font-size:16px;margin:16px 0 8px}.muted{color:#afc5d5;font-size:14px}.status{padding:10px 12px;border-left:3px solid #f3c779;background:#332e22;color:#ffe0ad}.good{color:#a6ecc1}.bad{color:#ffbec3}.facts{display:grid;grid-template-columns:120px minmax(0,1fr);gap:8px}.facts dt{color:#afc5d5}.facts dd{margin:0;overflow-wrap:anywhere}ul{padding-left:22px;line-height:1.7}.actions{display:flex;flex-wrap:wrap;gap:10px}.actions a,.actions button{display:inline-flex;align-items:center;min-height:44px}textarea{display:block;width:100%;min-height:96px;resize:vertical;margin:8px 0}.card>label{display:block}details{margin-top:12px}summary{cursor:pointer;min-height:44px;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:300px;overflow:auto}.player-note{padding:8px 0}.identity{font-family:ui-monospace,monospace;font-size:12px;overflow-wrap:anywhere}.snapshot{font-size:13px;margin-top:16px;color:#afc5d5}@media(max-width:950px){.layout{grid-template-columns:1fr}iframe{height:65vh;min-height:520px}}@media(max-width:540px){header,main{padding:14px}.toolbar>label{width:100%;justify-content:space-between}.toolbar select{min-width:140px}.facts{grid-template-columns:100px 1fr}h1{font-size:20px}iframe{min-height:440px}}
</style>
<header><h1>M5 联合动画集中验收</h1><p>三角色 × 呼吸 / 挥手。检查基础表情、发束摆动和裙袖响应是否与身体动作自然衔接。</p>
<p class="muted">使用官方 Spine 播放器与当前联合包。旧 M4 身体动作的接受记录不作为本次 M5 接受；技术检查与视觉复核分别记录。</p></header>
<main><div class="toolbar"><label>角色<select id="character" aria-label="角色"></select></label><label>动作<select id="motion" aria-label="动作"></select></label>
<a id="editor" target="_blank" rel="noopener">编辑此联合候选</a></div><div id="overview" class="overview" aria-live="polite"></div>
<div class="layout" style="margin-top:18px"><section><h2 id="title"></h2><iframe id="player" title="官方 Spine 联合动画播放器" allow="fullscreen"></iframe>
<p class="player-note muted">在播放器内播放、暂停或拖动时间轴。依次检查眼口、发根、袖口和裙腰，以及发—眼、袖—手、裙—腿的遮挡。</p>
<div class="actions"><a id="standalone" target="_blank" rel="noopener">独立窗口播放</a><a id="download">下载当前联合 Spine 包</a></div></section>
<aside><section class="card"><h2>当前联合候选</h2><p id="stage" class="status"></p><dl id="facts" class="facts"></dl><div id="effects"></div><details><summary>精确候选身份</summary><p id="identity" class="identity"></p></details></section>
<section class="card"><h2>技术异常与限制</h2><ul id="issues"></ul><p class="muted">Runtime 几何通过不等于画面已经接受。原有 M4 异常不会因添加表情或次级运动而消失。</p><details><summary>原始技术快照</summary><pre id="raw"></pre></details></section>
<section class="card"><h2>M5 阶段复核草稿</h2><label>本次结论<select id="verdict" aria-label="M5 阶段结论"><option value="not_reviewed">尚未复核</option><option value="stage_acceptable">阶段可接受，保留技术异常</option><option value="needs_changes">存在视觉异常，需调整</option></select></label>
<label>异常或限制备注<textarea id="notes" maxlength="4000" placeholder="可填写部位、动作时间和表现；例如 1.2 秒右袖与手掌穿插。"></textarea></label>
<div class="actions"><button id="save">保存当前复核草稿</button><button id="export">下载六样本复核草稿</button></div><p id="save-state" role="status" aria-live="polite" class="muted"></p>
<p class="muted">草稿仅保存在此浏览器，并绑定精确联合候选版本；不修改服务器接受记录，不触发发布。更换角色或动作前请保存。</p></section></aside></div>
<p id="snapshot" class="snapshot"></p></main>
<script id="snapshot-data" type="application/json">__SNAPSHOT__</script>
<script>
const data=JSON.parse(document.getElementById('snapshot-data').textContent),$=id=>document.getElementById(id);
const names={disabled:'未启用',applied:'已应用',partial:'部分应用',blocked:'未能应用',sampled_candidate_requires_visual_review:'已生成（阶段结论见上方）',passed:'通过',needs_changes:'需处理',not_requested:'未要求循环',not_evaluated:'未复核',needs_review:'已捕获（阶段结论见上方）',unavailable:'尚无有效捕获'};
const reasons={joint_secondary_channel_incomplete:'部分次级运动通道未应用',joint_face_material_incomplete:'部分面部素材不兼容',joint_animation_loop_needs_changes:'联合循环首尾仍有异常',joint_animation_deformation_needs_changes:'联合网格变形检查失败',motion_visible_depth_needs_changes:'前后遮挡仍需处理',camera_inertia_requires_unprojected_body_driver:'动态视角下惯性尚未分离，本次未添加对应响应',new_response_suppressed_for_geometry:'为保护网格，已关闭本区域新增响应'};
const contactNames={not_evaluated:'尚未验证',not_requested:'未要求',sampled_pass:'限定采样通过',passed:'通过',source_contact_unmeasured:'来源接触缺测',drift:'存在滑移',needs_changes:'存在异常'};
let current=null;const drafts=new Map();
const key=s=>`autospine:m5-stage-review:${s.job_id}:${s.artifact_sha256}`;
for(const s of data.samples){try{const saved=JSON.parse(localStorage.getItem(key(s))||'null');if(saved?.job_id===s.job_id&&saved?.artifact_sha256===s.artifact_sha256&&['not_reviewed','stage_acceptable','needs_changes'].includes(saved.verdict))drafts.set(s.job_id,saved);}catch{}}
for(const [value,label]of Object.entries(data.characters))$('character').add(new Option(label,value));for(const [value,label]of Object.entries(data.motions))$('motion').add(new Option(label,value));
function overview(){const rows=[`联合候选 ${data.samples.length}/6`,`Runtime 几何通过 ${data.samples.filter(s=>s.runtime.geometry_status==='passed').length}/6`,`服务器阶段接受 ${data.samples.filter(s=>['accepted','accepted_with_exceptions'].includes(s.server_review?.decision)).length}/6`,`已保存本地复核草稿 ${[...drafts.values()].filter(d=>d.verdict!=='not_reviewed').length}/6`];$('overview').replaceChildren(...rows.map(text=>{const span=document.createElement('span');span.textContent=text;return span;}));}
function stageText(s,draft){const row=s.server_review;if(row)return `服务器已保存 M5 阶段验收：${({accepted:'可接受',accepted_with_exceptions:'可接受，保留技术异常',rejected:'需调整',revoked:'已撤销'})[row.decision]} · r${row.revision}。本地草稿不更改此记录。`;
  return draft?.verdict==='stage_acceptable'?'本地 M5 草稿：阶段可接受（技术异常保留）':draft?.verdict==='needs_changes'?'本地 M5 草稿：存在视觉异常':'M5 视觉待复核；旧身体动作的接受结论不迁移。';}
function fact(label,value,ok){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;dd.className=ok===true?'good':ok===false?'bad':'';$('facts').append(dt,dd);}
function render(){current=data.samples.find(s=>s.character===$('character').value&&s.motion===$('motion').value);const s=current,base=`${data.base_url}/api/motions/${s.job_id}`;
  $('title').textContent=`${s.character_label} · ${s.motion_label} · M5 联合动画`;$('player').src=base+'/view/player.html';$('standalone').href=base+'/view/player.html';$('download').href=base+'/download';
  $('editor').href=data.base_url+'/motion-editor.html?joint='+encodeURIComponent(s.job_id);
  $('facts').replaceChildren();fact('原身体保留',s.preservation.passed?'检查通过':'未通过或缺测',s.preservation.passed===true);fact('联合几何',s.geometry_passed?'检查通过':'未通过或缺测',s.geometry_passed===true);
  fact('Runtime',`${names[s.runtime.geometry_status]||s.runtime.geometry_status||'缺测'} · ${s.runtime.frames??0} 帧`,s.runtime.geometry_status==='passed');
  fact('脸部',names[s.face.status]||s.face.status||'缺测');fact('发束 / 裙袖',names[s.secondary.status]||s.secondary.status||'缺测');fact('联合循环',names[s.loop.status]||s.loop.status||'缺测');
  const bodyLoop=s.loop.source_body?.loop_ready,effectLoop=s.loop.added_effects?.passed;
  fact('原身体循环',!s.loop.requested?'非循环动作，未要求':bodyLoop===true?'检查通过':bodyLoop===false?'原动作尚未首尾闭合':'缺测',s.loop.requested?bodyLoop:undefined);
  fact('新增效果循环',!s.loop.requested?'非循环动作，未要求':effectLoop===true?'检查通过':effectLoop===false?'仍有首尾异常':'缺测',s.loop.requested?effectLoop:undefined);
  const enabled=Object.entries({face:'表情',hair:'发束',cloth:'裙袖'}).filter(([k])=>s.enabled[k]).map(([,v])=>v);$('effects').textContent=`请求启用：${enabled.join('、')||'无'}。${s.mouth_template_enabled?(s.mouth_uploaded?'使用上传的嘴部模板。':'使用程序绘制的基础开口模板。'):'使用原嘴部素材。'}`;
  $('identity').textContent=`联合任务 ${s.job_id}\n联合包 ${s.artifact_sha256}\n身体来源 ${s.parent_job_id}\n身体包 ${s.parent_artifact_sha256}`;
  if(s.server_review)$('identity').textContent+=`\n服务器验收证据 ${s.server_review.evidence_sha256}\n验收时间 ${s.server_review.created_at}`;
  const issues=[];for(const row of s.issues){const code=typeof row==='string'?row:row.reason_code||row.reason||row.code;issues.push(reasons[code]||code||JSON.stringify(row));}
  for(const row of s.secondary.skipped||[])issues.push(`${row.slot||'次级运动'}：${reasons[row.reason]||row.reason}`);
  for(const row of s.secondary.regions||[]){const a=row.requested_config?.strength,b=row.effective_config?.strength;if(Number.isFinite(a)&&Number.isFinite(b)&&b<a)issues.push(`${row.slot}：网格保护将响应强度从 ${Number(a.toFixed(4))} 降为 ${Number(b.toFixed(4))}。`);}
  if(s.face.missing?.length)issues.push(`面部缺项：${s.face.missing.join('、')}`);if(s.contact_status)issues.push(`接触：${contactNames[s.contact_status]||s.contact_status}`);
  if(s.depth_order_status)issues.push(`遮挡：${['accepted','accepted_with_exceptions'].includes(s.server_review?.decision)?'阶段已接受，技术遮挡限制与缺测保留':s.depth_order_status==='joint_overlap_requires_visual_review'?'新增联合效果仍需视觉复核':s.depth_order_status}`);
  if(s.loop.requested&&bodyLoop===false)issues.push('原身体动作尚未满足循环检查；它不会因叠加联合效果自动闭合。请单独查看新增效果循环结论。');
  if(s.inherited_issue_context?.issue_count)issues.push(`保留 ${s.inherited_issue_context.issue_count} 项身体来源异常。`);
  issues.push('眨眼使用原睫毛压缩与显隐，有限五官位移不代表真实侧脸；发束与裙袖为有界平面响应。');
  $('issues').replaceChildren(...[...new Set(issues)].map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));$('raw').textContent=JSON.stringify(s,null,2);
  const draft=drafts.get(s.job_id);$('verdict').value=draft?.verdict||'not_reviewed';$('notes').value=draft?.notes||'';$('save-state').textContent=draft?'已恢复此联合候选的本地复核草稿。':'此联合候选尚无 M5 复核草稿。';
  $('stage').textContent=stageText(s,draft);overview();}
$('character').onchange=$('motion').onchange=render;
$('save').onclick=()=>{const value={schema:'autospine.m5-stage-review-draft/v1',job_id:current.job_id,artifact_sha256:current.artifact_sha256,character:current.character,motion:current.motion,verdict:$('verdict').value,notes:$('notes').value,saved_at:new Date().toISOString(),authority:'local_draft_only'};try{localStorage.setItem(key(current),JSON.stringify(value));drafts.set(current.job_id,value);$('save-state').textContent='当前 M5 复核草稿已保存；尚未提交服务器。';$('stage').textContent=stageText(current,value);overview();}catch(error){$('save-state').textContent='草稿保存失败：'+error.message;}};
$('export').onclick=()=>{const value={schema:'autospine.m5-cohort-review-draft/v1',snapshot_generated_at:data.generated_at,authority:'local_draft_only',records:data.samples.map(s=>drafts.get(s.job_id)||{job_id:s.job_id,artifact_sha256:s.artifact_sha256,character:s.character,motion:s.motion,verdict:'not_reviewed'})};const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='m5-six-sample-review-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('snapshot').textContent=`技术快照：${data.generated_at}。此页固定六个联合候选；参数更改或重新构建后需生成新快照。`;render();
</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('tmp/m5-joint/final-review/index.html'))
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    parser.add_argument('--acceptance', type=Path, help='Exact server stage-review snapshot for the six candidates')
    args = parser.parse_args()
    acceptance = json.loads(args.acceptance.read_bytes()) if args.acceptance else None
    snapshot = freeze(json.loads(args.input.read_bytes()), args.state_root, acceptance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(snapshot), encoding='utf-8')
    args.output.with_name('snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(output=str(args.output), samples=len(snapshot['samples']), visual_status=snapshot['visual_status'])))


if __name__ == '__main__':
    main()
