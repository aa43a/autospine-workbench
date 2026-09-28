"""Deliver an isolated playable window experiment, retaining inherited failures."""
import argparse
from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.sleeve_capture_environment import discover
from m4_order_window_candidate import compile_window
from m4_motion_delivery_check import verify_archive


def verify_capture(capture, fixture):
    rows=capture['rows']; times=[r['time'] for r in rows]
    if len(times)!=len(set(times)) or not {r['time'] for r in fixture['rows']}<=set(times):
        raise ValueError('order_window_delivery_capture_schedule')
    if any(r['vertex_delta']!=0 or r['newly_below_alpha_eight'] or r['maximum_alpha_delta']>1
           or not r['inside'] and r['maximum_channel_delta']!=0 for r in rows):
        raise ValueError('order_window_delivery_regression')
    if (len(capture['switches'])!=2 or any(s['changed_pixels'] for s in capture['switches'])
            or capture['switch_sample_status']!='no_change_over_one_channel_unit'):
        raise ValueError('order_window_delivery_switch_unverified')


def run(candidate, fixture_path, source_store, output):
    if output.exists(): raise ValueError('output_exists')
    receipt_raw=(candidate/'report.json').read_bytes(); receipt=json.loads(receipt_raw)
    raw=(candidate/'skeleton.json').read_bytes(); document=json.loads(raw)
    capture_raw=(candidate/'switch-runtime-v2.json').read_bytes(); capture=json.loads(capture_raw)
    fixture_raw=fixture_path.read_bytes(); fixture=json.loads(fixture_raw); window=receipt['window']
    if (sha256(raw).hexdigest()!=receipt['skeleton_sha256'] or capture['candidate_sha256']!=receipt['skeleton_sha256']
            or capture['receipt_sha256']!=sha256(receipt_raw).hexdigest()
            or receipt['fixture_sha256']!=sha256(fixture_raw).hexdigest()
            or capture['fixture_sha256']!=receipt['fixture_sha256']
            or document!=compile_window(fixture['skeleton'],window['region'],window['after_slot'],window['start'],window['end'])
            or capture.get('selected') is not False or capture.get('production_authorized') is not False):
        raise ValueError('order_window_delivery_identity')
    verify_capture(capture,fixture)
    source=AnimatedStore(source_store).read(receipt['source_artifact_sha256'])
    inherited={n:raw for n,raw in source.items() if n in ('deformation.json','motion-contact.json','motion-depth.json',
        'motion-moving-ankles.json','motion-projection.json','motion-review.json','motion-torso-projection.json')}
    if len(inherited)!=7:raise ValueError('order_window_inherited_evidence_missing')
    manifest=dict(schema='autospine.order-window-diagnostic/v1',authority='none',production_authorized=False,
        selected=False,source_artifact_sha256=receipt['source_artifact_sha256'],window=window,
        status='diagnostic_inherited_projection_geometry_and_depth_failures',
        inherited_evidence_scope='unchanged_parent_findings_not_relabelled_as_new_candidate_passes',
        runtime_scope=capture['scope'],runtime_version=capture['runtime_version'],target_spine='4.3.26')
    files={n:b for n,b in source.items() if n.endswith('.png') or n=='skeleton.atlas'}
    files.update({'skeleton.json':raw,'diagnostic-manifest.json':canonical_bytes(manifest),
                  'order-window.json':receipt_raw,'switch-runtime.json':capture_raw})
    files.update({'inherited-evidence/'+n:b for n,b in inherited.items()})
    env=discover(Path.cwd().parent)
    if not env:raise ValueError('order_window_runtime_missing')
    runtime=(Path(env[1])/'node_modules/@esotericsoftware/spine-webgl/dist/iife/spine-webgl.js').read_bytes()
    if sha256(runtime).hexdigest()!=capture['runtime_sha256']:raise ValueError('order_window_runtime_identity')
    store=AnimatedStore(output/'isolated-store'); digest=store.publish(files)
    output.mkdir(parents=True,exist_ok=True); assets=output/'player-assets'; assets.mkdir(exist_ok=False)
    page=Path('web/character-player.html').read_text(encoding='utf-8')
    page=page.replace('整角色动画验收','拳击局部排序 · 诊断候选').replace('原始捕获帧','候选说明')
    page=page.replace('<a href="setup/index.html">源图对照</a>','<a href="candidate.zip" download>下载诊断包</a>')
    page=page.replace('</header>','<p>仅调整 0.45–0.617 秒的手腿顺序。原有投影、几何与遮挡异常仍存在，未采用。</p></header>')
    (output/'player.html').write_text(page,encoding='utf-8')
    for name,source_name in [('client.js','character-player.js'),('inspection.js','character-player-inspection.js'),('style.css','character-player.css')]:
        (assets/name).write_bytes((Path('web')/source_name).read_bytes())
    (assets/'runtime.js').write_bytes(runtime)
    scene=dict(artifact_sha256=digest,info=fixture['info'],skeleton=document,atlas=source['skeleton.atlas'].decode(),
               textures={n:'data:image/png;base64,'+b64encode(b).decode() for n,b in files.items() if n.startswith('textures/') and n.endswith('.png')})
    (assets/'scene.json').write_bytes(canonical_bytes(scene))
    with ZipFile(output/'candidate.zip','x',compression=ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):archive.writestr(name,data)
    archive_raw=(output/'candidate.zip').read_bytes(); count=verify_archive(archive_raw,store.read(digest))
    report=dict(manifest,candidate_bundle_sha256=digest,skeleton_sha256=receipt['skeleton_sha256'],
                switch_report_sha256=sha256(capture_raw).hexdigest(),archive_sha256=sha256(archive_raw).hexdigest(),archive_files=count)
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'switch-runtime.json').write_bytes(capture_raw)
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>拳击时间窗口候选</title>'
        '<style>body{font:18px/1.7 system-ui;max-width:900px;margin:40px auto;background:#14202b;color:#eef}a{color:#7cceff}</style>'
        '<h1>拳击手腿排序 · 独立诊断候选</h1><p><a href="player.html">打开可拖动时间轴的播放器</a> · '
        '<a href="candidate.zip" download>下载诊断包</a></p><p>仅在 0.45–0.617 秒调整右手局部与腿的前后关系，窗口外保持原样。</p>'
        '<p>167 个时刻已做官方 Runtime 对照；两个关键帧同姿态顺序差最大为 1/255。此结果不修复原有网格翻转、投影方向及其他遮挡异常。</p>'
        '<p>未自动采用。源证据完整放在下载包 inherited-evidence 中，不作为当前候选通过证明。</p>'
        '<p><a href="report.json">包体与状态</a> · <a href="switch-runtime.json">切换采样证据</a></p>',encoding='utf-8')
    print(json.dumps(dict(bundle=digest,archive_files=count,output=str(output))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','fixture','source_store','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.candidate,a.fixture,a.source_store,a.output)
