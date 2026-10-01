"""Exercise the real workbench queue, immutable bundle and Runtime evidence."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('body')
    parser.add_argument('--base', default='http://127.0.0.1:8918')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--strength', default=25., type=float)
    parser.add_argument('--direction', default=30., type=float)
    parser.add_argument('--existing', help='Verify an already built wind job without rebuilding')
    args = parser.parse_args()
    def get(path, data=None):
        req = Request(args.base+path, data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json', 'X-Autospine-Intent':'pipeline-preview', 'Origin':args.base})
        with urlopen(req, timeout=90) as response: return response.read()
    job = args.existing
    if not job:
        meta = json.loads(get(f'/api/motions/{args.body}/joint-animation'))
        cfg = meta['defaults']; cfg['wind'].update(enabled=True, strength=args.strength, direction=args.direction, seed=713)
        for kind in ('hair', 'cloth', 'objects'):
            cfg[kind]['slots'] = [r['slot'] for r in meta['inventory'][kind] if r['state']=='available']
            cfg[kind]['enabled'] = bool(cfg[kind]['slots'])
        cfg['hair']['cascade'] = True
        row = json.loads(get(f'/api/motions/{args.body}/joint-animation', dict(artifact_sha256=meta['artifact_sha256'], config=cfg)))
        job = row.get('job', row)['job_id']; print(json.dumps(dict(job_id=job, status='submitted')), flush=True)
    last = None
    while True:
        row = json.loads(get(f'/api/motions/{job}')); row = row.get('job',row)
        progress = (row['status'], row.get('step'))
        if last != progress:
            print(json.dumps(dict(job_id=job,status=progress[0],step=progress[1])),flush=True); last=progress
        if row['status'] not in ('pending','running'): break
        time.sleep(2)
    if row['status'] != 'succeeded': raise RuntimeError(row.get('reason_code','wind_build_failed'))
    assert row['result']['joint_parent_job_id'] == args.body
    report = json.loads(get(f'/api/motions/{job}/view/joint-animation.json'))
    preview_raw = get(f'/api/motions/{job}/view/wind-preview.json'); preview = json.loads(preview_raw)
    assert sha256(preview_raw).hexdigest() == report['secondary']['wind_preview']['sha256']
    assert preview['config_sha256'] == report['config_sha256']
    assert report['secondary']['root_error_px'] < 1e-7
    assert report['preservation']['passed']
    archive_raw = get(f'/api/motions/{job}/download')
    with ZipFile(BytesIO(archive_raw)) as archive:
        skeleton_raw = archive.read('skeleton.json')
        assert sha256(skeleton_raw).hexdigest() == report['skeleton_sha256']
        assert archive.read('wind-preview.json') == preview_raw
        skeleton = json.loads(skeleton_raw); animation = skeleton['animations'][report['animation']]
        for region in report['secondary']['regions']:
            for helper in region['helpers']: assert len(animation['bones'][helper]['rotate']) >= 2
    runtime = row['result']['runtime']
    assert runtime['geometry_failed_records'] == 0 and runtime['geometry_status'] == 'passed'
    images = [name for name in runtime['files'] if name.startswith('frames/') and name.endswith('.png')]
    assert images and runtime['scope'] == 'all_attachment_vertices_and_nonempty_unclipped_framebuffer'
    evidence = dict(schema='autospine.wind-delivery-check/v1', parent=args.body, job_id=job,
        artifact_sha256=row['result']['artifact_sha256'], config_sha256=report['config_sha256'],
        skeleton_sha256=report['skeleton_sha256'], preview_sha256=sha256(preview_raw).hexdigest(),
        preview_bytes=len(preview_raw), bundle_bytes=len(archive_raw), runtime_frames=runtime['frames'],
        runtime_captured_images=len(images), runtime_scope=runtime['scope'],
        runtime_contact_status=runtime.get('contact_status'),
        runtime_geometry_failed_records=runtime['geometry_failed_records'], root_error_px=report['secondary']['root_error_px'],
        regions=[{k:r.get(k) for k in ('slot','region_kind','peak_response_deg','peak_sampled_displacement_px','effective_gain')}
            for r in report['secondary']['regions']], wind=report['secondary']['wind'],
        inherited_issues=row['result']['issues'], visual_acceptance='not_evaluated',
        build_timing=row['result'].get('build_timing'), editor_url=args.base+'/motion-editor.html',
        player_url=args.base+f'/api/motions/{job}/view/player.html', passed=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(job_id=job, frames=runtime['frames'], passed=True, regions=len(evidence['regions']))),flush=True)


if __name__ == '__main__': main()
