"""Read actual M5 downloads back independently; never publish or mutate sources."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_joint_source import frozen_context
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read

NAMES = [f'{character}-{motion}' for character in ('alice', 'huiye', 'hongmeiling')
         for motion in ('breathing', 'wave')]


def unpack(raw):
    with ZipFile(BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('duplicate_export_entry')
        if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in names):
            raise ValueError('unsafe_export_entry')
        return {n: archive.read(n) for n in names}


def check_bundle(files, parent):
    document = json.loads(files['skeleton.json']); editor = json.loads(files['editor/skeleton.json'])
    joint = json.loads(files['joint-animation.json']); animation = joint['animation']
    for field in ('bones', 'slots', 'skins', 'animations'):
        if editor[field] != document[field]:
            raise ValueError('editor_identity_'+field)
    names = [b['name'] for b in document['bones']]
    if len(names) != len(set(names)):
        raise ValueError('duplicate_bone')
    for bone in document['bones']:
        if bone.get('parent') and names.index(bone['parent']) >= names.index(bone['name']):
            raise ValueError('bone_parent_order')
    if set(document['animations'][animation].get('bones', {}))-set(names):
        raise ValueError('unknown_bone_channel')
    image_paths = set()
    for slots in document['skins'][0]['attachments'].values():
        for attachment in slots.values():
            name = 'images/'+attachment['path']+'.png'; image_paths.add(name)
            if name not in files or files.get('editor/'+name) != files[name]:
                raise ValueError('editor_png_identity_'+name)
    pages = [line.strip() for line in files['skeleton.atlas'].decode().splitlines() if line.strip().endswith('.png')]
    if not pages or any(page not in files or not files[page].startswith(b'\x89PNG\r\n\x1a\n') for page in pages):
        raise ValueError('atlas_png_missing')
    old = json.loads(parent['skeleton.json'])
    old_bones = {b['name']: b for b in old['bones']}
    if any(b != old_bones[b['name']] for b in document['bones'] if b['name'] in old_bones):
        raise ValueError('source_bone_changed')
    replaced = set(joint['secondary'].get('probe_tracks_replaced', []))
    before = old['animations'][animation].get('bones', {}); after = document['animations'][animation].get('bones', {})
    changed = [name for name in old_bones if before.get(name) != after.get(name)]
    if set(changed)-replaced:
        raise ValueError('source_channel_changed_'+','.join(sorted(set(changed)-replaced)))
    for name, raw in parent.items():
        if name.endswith('.png') and files.get(name) != raw:
            raise ValueError('source_png_changed_'+name)
    if joint['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('skeleton_hash_mismatch')
    if joint['parent_skeleton_sha256'] != sha256(parent['skeleton.json']).hexdigest():
        raise ValueError('parent_hash_mismatch')
    before_mesh = old['skins'][0]['attachments']; after_mesh = document['skins'][0]['attachments']
    unaffected = sorted(slot for slot in before_mesh if before_mesh[slot] == after_mesh.get(slot))
    maximum = 0.
    for t in (0., joint['duration']*.137, joint['duration']*.51, joint['duration']*.923, joint['duration']):
        a = sample(old, animation, t)[0]; b = sample(document, animation, t)[0]
        maximum = max(maximum, max((math.dist(p, q) for slot in unaffected
            for p, q in zip(a[slot], b[slot], strict=True)), default=0.))
    if maximum > 1e-8:
        raise ValueError('unaffected_body_displaced')
    return dict(passed=True, bones=len(names), slots=len(document['slots']), atlas_pages=len(pages),
        editor_images=len(image_paths), source_pngs=sum(n.endswith('.png') for n in parent),
        main_editor_channels_identical=True, changed_existing_aux_tracks=changed,
        unaffected_slots=unaffected, unaffected_max_error_px=maximum,
        generated_templates=joint['face'].get('generated_templates', []))


def runtime_check(folder, files, artifact):
    report = json.loads((folder/'runtime/report.json').read_bytes())
    geometry = json.loads((folder/'runtime/deformation.json').read_bytes())
    if report['bundle_sha256'] != artifact or not report['passed']:
        raise ValueError('official_capture_identity_or_numeric_failure')
    expected = read(files)['animations']
    actual = {}
    for row in report['results']:
        actual.setdefault(row['animation'], []).append(row['time'])
    if actual != {k: [r['time'] for r in v] for k, v in expected.items()}:
        raise ValueError('runtime_sample_times_mismatch')
    screenshots = report.get('screenshots', [])
    for row in screenshots:
        if sha256((folder/'runtime'/row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('runtime_screenshot_hash_mismatch')
    return dict(numeric_passed=report['passed'], frames=len(report['results']), screenshot_count=len(screenshots),
        runtime_version=report['runtime_version'], profile=report['profile'], samples_match=True,
        max_error_px=max(r['max_error_px'] for r in report['results']), geometry_passed=geometry['passed'],
        geometry_failed_records=sum(not r['passed'] for r in geometry['records']),
        visual_acceptance='not_evaluated_by_this_tool')


def fixture(files, source, joint):
    document = json.loads(files['skeleton.json']); animation = joint['animation']; duration = joint['duration']
    times = sorted({0., duration, duration*.1, duration*.35, duration*.79, duration*.99,
                   *[min(duration, t) for t in (.5, .545, .59, .635, .68)]})
    return dict(skeleton=document, source_skeleton=json.loads(source['skeleton.json']),
        atlas=files['skeleton.atlas'].decode(), animation=animation, duration=duration,
        loop=joint['loop'], face=joint['face'], secondary=joint['secondary'],
        samples=[dict(time=t, vertices=sample(document, animation, t)[0]) for t in times])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs-dir', type=Path, default=Path('tmp/m5-joint'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8918')
    options = parser.parse_args(); state = Path('workspace'); store = AnimatedStore(state)
    results = []; options.output.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        path = options.jobs_dir/(name+'.json')
        final = options.jobs_dir/(name+'-final.json')
        if final.is_file(): path = final
        row = dict(name=name, status='pending')
        if path.is_file():
            job = json.loads(path.read_bytes()); row['job_id'] = job['job_id']
            if job.get('status') == 'succeeded':
                folder = state/'jobs/motion-intake-v1'/job['job_id']
                request = json.loads((folder/'request.json').read_bytes())
                source = frozen_context(state, request)['files']; artifact = job['result']['artifact_sha256']
                expected = store.read(artifact)
                try:
                    with urlopen(options.base_url+'/api/motions/'+job['job_id']+'/download', timeout=60) as response:
                        raw = response.read()
                    files = unpack(raw)
                    if files != expected: raise ValueError('download_not_stored_artifact')
                    if canonical_sha256({n:sha256(v).hexdigest() for n,v in files.items()}) != artifact:
                        raise ValueError('download_artifact_identity')
                    row.update(status='checked', artifact_sha256=artifact, download_sha256=sha256(raw).hexdigest(),
                        download_files=len(files), bundle=check_bundle(files, source),
                        runtime=runtime_check(folder, files, artifact))
                    joint = json.loads(files['joint-animation.json'])
                    row['loop'] = dict(status=joint['loop']['status'], source_ready=joint['loop']['source_body']['loop_ready'],
                        effects_passed=joint['loop']['added_effects']['passed'],
                        source_velocity_error=joint['loop']['source_body']['max_velocity_error_px_per_second'])
                    (options.output/(name+'.fixture.json')).write_bytes(canonical_bytes(fixture(files, source, joint)))
                except Exception as exc:
                    row.update(status='failed', reason=str(exc))
        results.append(row)
        print(json.dumps({k:row[k] for k in ('name','status','reason') if k in row}), flush=True)
    report = dict(profile='joint-delivery-independent-v1', requested=len(NAMES),
        checked=sum(r['status']=='checked' for r in results), results=results,
        passed=all(r['status']=='checked' and r['bundle']['passed'] and r['runtime']['geometry_passed'] for r in results),
        limitations=['Fresh CPU/offline export checks do not imply human visual acceptance.',
                     'Runtime screenshots are hash checked, not automatically visually accepted.'])
    (options.output/'delivery-report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(passed=report['passed'], checked=report['checked'], requested=len(NAMES))))


if __name__ == '__main__':
    main()
