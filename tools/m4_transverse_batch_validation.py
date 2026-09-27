"""Validate every saved transverse diagnostic time in bounded, independent batches."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.numeric_reference import carry_setup, read, write
from m4_runtime_batch_coverage import partition, render_identity
from m4_transverse_sampling_probe import inventory


def verify_diagnostic(original, raw, report, times):
    if sha256(raw).hexdigest() != report['skeleton_sha256'] or \
            sha256(canonical_bytes(times)).hexdigest() != report['times_sha256']:
        raise ValueError('transverse_batch_diagnostic_identity')
    before = json.loads(original['skeleton.json']); after = json.loads(raw)
    if set(after['animations']) != {'external-motion'}:
        raise ValueError('transverse_batch_animation')
    slot = report['slot']; normalized = []
    for doc in (before, after):
        value = deepcopy(doc)
        animation = value['animations']['external-motion']
        for skin in list(animation.get('attachments', {})):
            animation['attachments'][skin].pop(slot, None)
            if not animation['attachments'][skin]:del animation['attachments'][skin]
        if not animation.get('attachments'):animation.pop('attachments', None)
        normalized.append(value)
    if normalized[0] != normalized[1]:
        raise ValueError('transverse_batch_unselected_content_changed')
    expected = inventory(after, 'external-motion',
        [r['time'] for r in read(original)['animations']['external-motion']])['times']
    if expected != times:
        raise ValueError('transverse_batch_missing_required_times')
    return after


def prepare(original, raw, times):
    document = json.loads(raw); frames = []
    for time in times:
        frames.append(dict(time=time, vertices=sample(document, 'external-motion', time)[0]))
    files = {k:v for k,v in original.items() if k.endswith('.png') or k == 'skeleton.atlas'}
    files['skeleton.json'] = raw
    setup = carry_setup(original, files)
    if setup is None:raise ValueError('transverse_batch_setup_required')
    files = write(files, dict(skeleton_sha256=sha256(raw).hexdigest(),
        animations={'external-motion':frames}), compressed=True)
    geometry = inspect(files, setup_vertices=setup)
    files['deformation.json'] = canonical_bytes(geometry)
    manifest = json.loads(original['character-manifest.json'])
    manifest.update(status='needs_changes', authority='none', selected=False, production_authorized=False,
        files={k:sha256(v).hexdigest() for k,v in files.items()})
    files['character-manifest.json'] = canonical_bytes(manifest)
    return files, geometry


def normalized_diagnostic(original, raw, report, times):
    document = verify_diagnostic(original, raw, report, times)
    from autospine_workbench.targets.character43.deform_time_aliases import normalize
    result, evidence = normalize(document, json.loads(original['skeleton.json']), 'external-motion', report['slot'])
    # Retain the entire original diagnostic grid, including every removed key.
    required = sorted(set(times) | set(inventory(result, 'external-motion', [])['times']))
    return canonical_bytes(result), required, evidence


def verify_coverage(times, rows, runtime=False):
    covered = []; identities = set(); implementations = set()
    for index, row in enumerate(rows):
        actual = row['times']
        if not actual or actual[0] != 0:
            raise ValueError('transverse_batch_anchor_missing')
        covered.extend(actual[1:] if index else actual)
        identities.add(row['render_identity'])
        if runtime:
            result = row['runtime']
            fields = ('runtime_sha256','runtime_version','profile','browser_sha256',
                      'harness_sha256','tool_sha256','reference_reader_sha256')
            if (result['bundle_sha256'] != row['candidate_bundle_sha256'] or result.get('passed') is not True
                    or result.get('authority') != 'none' or result.get('production_authorized') is not False
                    or any(not isinstance(result.get(k), str) or not result[k] for k in fields)
                    or [r['time'] for r in result['results']] != actual
                    or any(r['animation'] != 'external-motion' for r in result['results'])):
                raise ValueError('transverse_batch_runtime_mismatch')
            implementations.add(tuple(result[k] for k in fields))
    if covered != times or len(identities) != 1 or runtime and len(implementations) != 1:
        raise ValueError('transverse_batch_coverage_mismatch')
    return dict(frames=len(times), batches=len(rows), exact_time_coverage=True,
        geometry_passed=all(r['geometry_passed'] for r in rows),
        runtime_status='passed' if runtime else 'not_evaluated',
        authority='none', selected=False, production_authorized=False)


def run(state_root, probe, output, *, runtime=False):
    report = json.loads((probe/'report.json').read_bytes())
    raw = (probe/'solved-diagnostic.json').read_bytes()
    times = json.loads((probe/'validation-times.json').read_bytes())
    original = AnimatedStore(state_root).read(report['parent_artifact_sha256'])
    raw, times, normalization = normalized_diagnostic(original, raw, report, times)
    chunks = partition(times, size=1024)
    output.mkdir(parents=True, exist_ok=False); rows = []
    receipt = dict(status='running', parent_artifact_sha256=report['parent_artifact_sha256'],
        skeleton_sha256=sha256(raw).hexdigest(), diagnostic_skeleton_sha256=report['skeleton_sha256'],
        normalization=normalization, probe_sha256=sha256((probe/'report.json').read_bytes()).hexdigest(),
        required_times=times, pending_checks=['contact', 'depth', 'visual'], authority='none', selected=False,
        production_authorized=False, rows=rows)
    def save(): (output/'report.json').write_bytes(canonical_bytes(receipt))
    save()
    try:
        for index, chunk in enumerate(chunks):
            folder = output/f'batch-{index:03d}'; folder.mkdir()
            print(json.dumps(dict(batch=index, total=len(chunks), stage='geometry', samples=len(chunk))), flush=True)
            files, geometry = prepare(original, raw, chunk)
            parent_files, parent_geometry = prepare(original, original['skeleton.json'], chunk)
            if render_identity(parent_files) != render_identity(original):
                raise ValueError('transverse_batch_parent_changed')
            del parent_files
            evidence = dict(parent_geometry=parent_geometry, geometry=geometry, times=chunk)
            (folder/'geometry.json').write_bytes(canonical_bytes(evidence))
            store = AnimatedStore(folder/'isolated-store'); digest = store.publish(files)
            row = dict(folder=folder.name, candidate_bundle_sha256=digest, times=chunk,
                render_identity=render_identity(files), geometry_passed=geometry['passed'],
                geometry_sha256=sha256(canonical_bytes(evidence)).hexdigest())
            del files
            if runtime:
                result = capture(SimpleNamespace(workspace_root=Path.cwd().parent), store, digest, folder,
                    progress=lambda stage:print(json.dumps(dict(batch=index,stage=stage)),flush=True),
                    cancel_requested=lambda:False, storage_reference=True)
                if result['status'] == 'unavailable':raise ValueError('transverse_batch_runtime_unavailable')
                row['runtime'] = json.loads((folder/'runtime/report.json').read_bytes())
            rows.append(row); save()
            verify_coverage(chunk, [row], runtime)
        receipt.update(status='complete', coverage=verify_coverage(times, rows, runtime))
        save()
        from m4_transverse_batch_audit import audit
        audit(state_root, probe, output)
        print(json.dumps(receipt['coverage']), flush=True)
    except Exception as exc:
        receipt.update(status='failed', error=str(exc)); save(); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('state_root','probe','output'):parser.add_argument(name, type=Path)
    parser.add_argument('--runtime', action='store_true')
    args = parser.parse_args(); run(args.state_root, args.probe, args.output, runtime=args.runtime)
