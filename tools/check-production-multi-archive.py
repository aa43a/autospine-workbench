"""Check a downloaded delivery against its immutable source bundles and capture."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--archive', required=True)
    parser.add_argument('--state-root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with ZipFile(args.archive) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist())), 'duplicate ZIP entries'
        files = {name: archive.read(name) for name in archive.namelist()}
    record = json.loads(files.pop('delivery/record.json'))
    raw = files.pop('delivery/runtime-report.json')
    assert sha256(raw).hexdigest() == record['runtime']['files']['report.json']
    runtime = json.loads(raw)
    store = AnimatedStore(Path(args.state_root))
    assert files == store.read(record['artifact_sha256']), 'download differs from stored bundle'
    assert runtime['bundle_sha256'] == record['artifact_sha256']
    merged = json.loads(files['skeleton.json'])
    reference = read(files)
    report = json.loads(files['multi-animation.json'])
    assert [s['artifact_sha256'] for s in report['sources']] == [
        s['artifact_sha256'] for s in record['request']['sources']]
    checked = []
    for source in report['sources']:
        original = store.read(source['artifact_sha256'])
        skeleton = json.loads(original['skeleton.json'])
        original_reference = read(original)
        for name, alias in source['animation_mapping'].items():
            assert merged['animations'][alias] == skeleton['animations'][name], alias
            assert reference['animations'][alias] == original_reference['animations'][name], alias
            checked.append(alias)
        for name, evidence in source['evidence'].items():
            assert files[evidence['file']] == original[name], name
    assert set(checked) == set(merged['animations'])
    result = dict(passed=True, job_id=record['job_id'], artifact_sha256=record['artifact_sha256'],
        animations=checked, exact_tracks_and_references=True, source_evidence_preserved=True,
        runtime_frames=record['runtime']['frames'], visual_status=record['visual_status'])
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
