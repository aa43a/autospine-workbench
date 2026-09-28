"""Independent module toggles and deterministic compilation on a frozen source."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

from autospine_workbench.automation.motion_joint_source import frozen_context
from autospine_workbench.automation.motion_joint_inheritance import review
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43 import joint_face, joint_secondary
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.joint_spring import grid


def compose(files, document, animation, config, duration, camera_keys=None):
    times = grid(duration, 60)
    output, updates, face = joint_face.apply(files, document, animation, config['face'], times)
    output, secondary = joint_secondary.apply(files, output, animation,
        {k:config[k] for k in ('hair', 'cloth', 'loop')}, times, camera_keys=camera_keys)
    return output, updates, face, secondary


def inspect(files, config, animation, duration, camera_keys=None):
    source = json.loads(files['skeleton.json']); initial_hash = canonical_sha256({n:sha256(v).hexdigest() for n,v in files.items()})
    variants = {}; reports = []; times = [duration*v for v in (0., .11, .35, .59, .83, 1.)]
    for disabled in ('none', 'all', 'face', 'hair', 'cloth'):
        controls = deepcopy(config)
        for name in ('face', 'hair', 'cloth'):
            if disabled in ('all', name): controls[name]['enabled'] = False
        doc, updates, face, secondary = compose(files, source, animation, controls, duration, camera_keys)
        variants[disabled] = (doc, updates, face, secondary)
        if disabled == 'all':
            if doc != source or canonical_bytes(doc) != files['skeleton.json'] or updates:
                raise ValueError('all_off_not_exact_source')
        before = source['animations'][animation].get('bones', {}); after = doc['animations'][animation].get('bones', {})
        changed = [b['name'] for b in source['bones'] if before.get(b['name']) != after.get(b['name'])]
        if set(changed)-set(secondary.get('probe_tracks_replaced', [])):
            raise ValueError('unexpected_body_track_change')
        affected = set(face.get('affected_slots', [])) | set(secondary.get('affected_slots', []))
        unaffected = set(source['skins'][0]['attachments'])-affected
        maximum = 0.
        for t in times:
            a, b = sample(source, animation, t)[0], sample(doc, animation, t)[0]
            maximum = max(maximum, max((math.dist(p,q) for slot in unaffected
                for p,q in zip(a[slot], b[slot], strict=True)), default=0.))
        if maximum > 1e-8: raise ValueError('toggle_changed_unaffected_vertices')
        prefixes = {'face': ('m5-face-',), 'hair': ('m5-hair-',), 'cloth': ('m5-response-',)}
        if disabled in prefixes and any(b['name'].startswith(prefixes[disabled]) for b in doc['bones']):
            raise ValueError('disabled_channel_helpers_remain')
        if disabled in ('all', 'face') and updates: raise ValueError('disabled_face_assets_remain')
        reports.append(dict(disabled=disabled, passed=True, body_tracks_preserved=True,
            replaced_aux_probes=changed, unaffected_slots=len(unaffected), max_body_error_px=maximum,
            generated_assets=len(updates), source_exact=disabled=='all'))
    baseline = variants['none'][0]
    for disabled in ('face', 'hair', 'cloth'):
        current = variants[disabled][0]
        for channel in ('face', 'hair', 'cloth'):
            if channel == disabled: continue
            prefix = {'face':'m5-face-', 'hair':'m5-hair-', 'cloth':'m5-response-'}[channel]
            original = {n:t for n,t in baseline['animations'][animation].get('bones', {}).items() if n.startswith(prefix)}
            actual = {n:t for n,t in current['animations'][animation].get('bones', {}).items() if n.startswith(prefix)}
            if original != actual: raise ValueError('toggle_changed_enabled_sibling_'+channel)
    if initial_hash != canonical_sha256({n:sha256(v).hexdigest() for n,v in files.items()}):
        raise ValueError('source_asset_map_mutated')
    return dict(passed=True, variants=reports, source_assets_unchanged=True,
                surviving_helper_tracks_identical=True, probe_times=times)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--determinism', action='store_true')
    options = parser.parse_args(); job = json.loads(options.job.read_bytes())
    request = json.loads((Path('workspace/jobs/motion-intake-v1')/job['job_id']/'request.json').read_bytes())
    source = frozen_context('workspace', request); cfg = request['joint_execution']; camera = request.get('projection', {}).get('keys')
    result = inspect(source['files'], cfg['config'], cfg['animation'], cfg['duration'], camera)
    if options.determinism:
        from autospine_workbench.targets.character43.joint_animation import build
        builds = [build(source['files'], cfg['config'], camera_keys=camera, parent_review=review(source))[0] for _ in range(2)]
        if builds[0] != builds[1]:
            raise ValueError('repeated_build_bytes_changed')
        result['determinism'] = dict(passed=True, builds=2, files=len(builds[0]),
            bytes=sum(len(v) for v in builds[0].values()),
            artifact_sha256=canonical_sha256({n:sha256(v).hexdigest() for n,v in builds[0].items()}),
            scope='CPU compiler before job provenance, depth and Runtime capture')
    result.update(job_id=job['job_id'], source_artifact_sha256=source['artifact_sha256'],
                  animation=cfg['animation'], duration=cfg['duration'])
    options.output.parent.mkdir(parents=True, exist_ok=True); options.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
