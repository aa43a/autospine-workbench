"""Read-only collection of exact candidate bundles and their sampled evidence."""
import hashlib
import json
from pathlib import Path, PurePosixPath

from ..resolved_project import canonical_sha256
from .elbow_target_cli import archive
from .seam_admission_cli import read_admission


def summarize(character, candidate, admission):
    if character not in ('alice', 'crino', 'lingxian'):
        raise ValueError('hub_character')
    if candidate['schema'] != 'autospine.seam-stable-fallback/v1':
        raise ValueError('hub_candidate_schema')
    for report in (candidate, admission):
        if report['authority'] != 'none' or report['production_authorized'] is not False:
            raise ValueError('hub_review_only')
    if admission['source_candidate_sha256'] != canonical_sha256(candidate):
        raise ValueError('hub_candidate_identity')
    return dict(character=character, status='needs_review', authority='none',
                production_authorized=False, candidate_sha256=canonical_sha256(candidate),
                relations=[dict(row, track=('reference' if row['follower'] in
                           candidate['followers'] else 'increment')) for row in admission['relations']])


def bundle_bytes(folder, inventory):
    result = {}
    folder = folder.resolve()
    for name, digest in inventory.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('hub_file_path')
        target = (folder / name).resolve()
        if not target.is_relative_to(folder):
            raise ValueError('hub_file_path')
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('hub_file_hash')
        result[name] = raw
    return result


def load_collection(config_path, runtime_path):
    config = json.loads(config_path.read_bytes())
    entries = config['characters']
    if not 1 <= len(entries) <= 3 or len({e['character'] for e in entries}) != len(entries):
        raise ValueError('hub_character_inventory')
    runtime_bytes = runtime_path.read_bytes()
    runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
    files, summaries = {'/runtime.js': runtime_bytes}, []
    for entry in entries:
        paths = {key: (config_path.parent / entry[key]).resolve()
                 for key in ('direct', 'runtime', 'candidate', 'manifest', 'admission')}
        candidate = json.loads(paths['candidate'].read_bytes())
        admission = json.loads(paths['admission'].read_bytes())
        runtime = json.loads(paths['runtime'].read_bytes())
        if runtime['runtime_sha256'] != runtime_sha or runtime['runtime_version'] != '4.3.13':
            raise ValueError('hub_runtime_identity')
        read_admission(admission, *(paths[k] for k in ('direct', 'runtime', 'candidate', 'manifest')))
        summary = summarize(entry['character'], candidate, admission)
        data = bundle_bytes(paths['manifest'].parent, candidate['files'])
        # Rebuilt from verified bytes; never trust a mutable sibling preview.zip.
        base = '/' + entry['character'] + '/'
        files.update({base + name: raw for name, raw in data.items()})
        files[base + 'preview.zip'] = archive(data)
        files[base + 'admission.json'] = json.dumps(admission).encode()
        summary['zip_sha256'] = hashlib.sha256(files[base + 'preview.zip']).hexdigest()
        summaries.append(summary)
    index = dict(status='needs_review', authority='none', production_authorized=False,
                 export_target='4.3.26', runtime_version='4.3.13', runtime_sha256=runtime_sha,
                 scope='existing_candidate_regions_only', characters=summaries)
    files['/collection.json'] = json.dumps(index).encode()
    return index, files
