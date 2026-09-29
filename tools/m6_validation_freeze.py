"""Freeze effective code, inputs and parameters before independent material runs."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED


def digest(path):
    h = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def code_files(root):
    files = [p for directory in ('src', 'web', 'tools') for p in (root/directory).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py', '.js', '.mjs', '.html', '.css', '.json')]
    files += [p for p in root.iterdir() if p.is_file() and
              (p.name == 'pyproject.toml' or p.name.endswith('.lock') or p.name.startswith('requirements'))]
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(files)}


def verify(manifest, root):
    current = code_files(root)
    changed = [name for name in set(current) | set(manifest['code'])
               if current.get(name) != manifest['code'].get(name)]
    inputs = [entry['path'] for entry in manifest['inputs']
              if not Path(entry['path']).is_file() or digest(entry['path']) != entry['sha256']]
    return dict(passed=not changed and not inputs, changed_code=sorted(changed), changed_inputs=inputs)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--input', action='append', default=[], help='PSD, model, source request/result or runtime dependency')
    parser.add_argument('--parameters', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.verify:
        result = verify(json.loads(args.verify.read_text(encoding='utf-8')), root)
        print(json.dumps(result)); raise SystemExit(0 if result['passed'] else 1)
    if not args.output or not args.parameters or not args.input:
        parser.error('creation requires --output, --parameters and --input')
    output = args.output.resolve()
    if output.exists():
        parser.error('freeze output already exists; choose a new version')
    code = code_files(root)
    inputs = [dict(path=str(Path(p).resolve()), sha256=digest(p)) for p in args.input]
    inputs.append(dict(path=str(args.parameters.resolve()), sha256=digest(args.parameters)))
    manifest = dict(schema='autospine.m6-validation-freeze/v1', created_at=datetime.now(timezone.utc).isoformat(),
        git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        code=code, inputs=inputs, parameters=json.loads(args.parameters.read_text(encoding='utf-8-sig')),
        scope='effective_files_including_uncommitted_changes_not_git_head_alone',
        independence='requires_separate_history_audit', human_time='not_measured', accepted=False)
    output.mkdir(parents=True)
    with ZipFile(output/'code.zip', 'x', ZIP_DEFLATED) as archive:
        for name, expected in code.items():
            raw = (root/name).read_bytes()
            if sha256(raw).hexdigest() != expected:
                raise RuntimeError('code changed while freezing')
            archive.writestr(name, raw)
    manifest['code_archive_sha256'] = digest(output/'code.zip')
    with (output/'freeze.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    result = verify(manifest, root)
    if not result['passed']:
        raise RuntimeError(json.dumps(result))
    print(json.dumps(dict(manifest=str(output/'freeze.json'), code_files=len(code), inputs=len(inputs))))


if __name__ == '__main__':
    main()
