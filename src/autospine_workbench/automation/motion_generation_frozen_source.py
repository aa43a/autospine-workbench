"""Pure source freeze plan and Git-free verification for an explicit Kimodo bundle.

Git is used only by the opt-in builder, with an absolute executable. A receipt
contains Git objects, not an asserted revision string: its two fixed commits and
complete trees are replayed before current source bytes are checked. The pinned
loader is a local PEFT fix on top of upstream, never described as upstream code.
This proves source integrity/provenance, not publisher signature or model quality.
"""
from base64 import b64decode, b64encode
from hashlib import sha1, sha256
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

from ..safe_input_files import read_real_file, strict_json_object
from .storage_io import canonical_bytes

SCHEMA = 'autospine.kimodo-frozen-source/v1'
BUILDER = 'fixed-git-object-source-freeze-v1'
RECEIPT = 'kimodo-source-provenance.json'
UPSTREAM_URL = 'https://github.com/nv-tlabs/kimodo'
UPSTREAM_REVISION = '1aece8c124d73d255ceff5086d983b844c9f4e94'
PINNED_REVISION = 'c503c77aa877f4e4469402ae197bb0e5739bbedd'
PATCH_NOTES = {
    'kimodo/model/llm2vec/llm2vec.py': 'Pinned local fix: attach the local PEFT adapter once.',
}
REQUIRED_SOURCE = ('LICENSE', 'ATTRIBUTIONS.MD', 'pyproject.toml',
                   'kimodo/scripts/generate.py', 'kimodo/model/llm2vec/llm2vec.py')
MAX_FILES = 4096
MAX_FILE_BYTES = 64 << 20
MAX_SOURCE_BYTES = 512 << 20
MAX_RECEIPT_BYTES = 2 << 20
_SHA1 = re.compile(r'[0-9a-f]{40}\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_CRLF_NOTE = 'CRLF checkout representation; normalized bytes match the pinned Git blob.'


def _fail(code='motion_generation_frozen_source_invalid'):
    raise ValueError(code)


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        _fail()


def _path(value):
    if type(value) is not str or not value or len(value) > 240:
        _fail()
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or '\\' in value:
        _fail()
    for part in path.parts:
        stem = part.split('.')[0].upper()
        if (part in ('.', '..', '.git') or part.endswith((' ', '.')) or
                any(c in part for c in ':<>"|?*') or any(ord(c) < 32 for c in part) or
                stem in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                         *(f'LPT{i}' for i in range(1, 10))}):
            _fail()
    return value


def _hash(value, expression):
    if type(value) is not str or expression.fullmatch(value) is None:
        _fail()


def _git_hash(kind, data):
    return sha1(kind.encode('ascii') + b' ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def _real_directory(path):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink() or
            getattr(info, 'st_file_attributes', 0) & 0x400):
        _fail('motion_generation_frozen_source_unsafe')


def _root(root):
    root = Path(os.path.abspath(os.fspath(root)))
    for directory in reversed((root, *root.parents)):
        _real_directory(directory)
    _real_directory(root / 'source')
    return root


def has_frozen_source_receipt(root):
    """An unreadable or dangling receipt must not select the legacy fallback."""
    try:
        (Path(root) / RECEIPT).lstat()
        return True
    except FileNotFoundError:
        # Some Windows reparse points report ENOENT for lstat as well. The
        # directory entry still makes this a present, invalid receipt.
        try:
            with os.scandir(root) as entries:
                return any(entry.name.casefold() == RECEIPT.casefold() for entry in entries)
        except OSError as exc:
            raise ValueError('motion_generation_source_unavailable') from exc
    except OSError as exc:
        raise ValueError('motion_generation_source_unavailable') from exc


def _record(path, relative):
    raw = read_real_file(path, MAX_FILE_BYTES, 'Kimodo frozen source')
    return dict(path=_path(relative), byte_length=len(raw), sha256=sha256(raw).hexdigest(),
                git_blob_sha1=_git_hash('blob', raw)), raw


def _generated(relative):
    parts = PurePosixPath(relative).parts
    if '__pycache__' in parts:
        return parts[-1].endswith('.pyc')
    return (parts[0] == 'kimodo.egg-info' and len(parts) == 2 and parts[1] in
            {'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'entry_points.txt',
             'requires.txt', 'top_level.txt', 'not-zip-safe'})


def _inventory(root, *, building=False):
    """Build excludes only known generated artifacts; runtime inventory is exact."""
    source, rows, contents, omitted = root / 'source', [], {}, []
    for directory, dirs, names in os.walk(source, followlinks=False):
        directory = Path(directory)
        for name in list(dirs):
            child = directory / name
            _real_directory(child)
            if name == '.git' and child.parent == source and building:
                dirs.remove(name)
                omitted.append('.git/')
            elif name == '.git':
                _fail('motion_generation_frozen_source_unsafe')
        for name in names:
            child = directory / name
            relative = child.relative_to(source).as_posix()
            if building and _generated(relative):
                read_real_file(child, MAX_FILE_BYTES, 'Kimodo generated build artifact')
                omitted.append(relative)
                continue
            row, raw = _record(child, relative)
            rows.append(row)
            contents[relative] = raw
            if len(rows) > MAX_FILES or sum(r['byte_length'] for r in rows) > MAX_SOURCE_BYTES:
                _fail('motion_generation_frozen_source_too_large')
    rows.sort(key=lambda r: r['path'])
    _validate_files(rows)
    if not set(REQUIRED_SOURCE).issubset(contents):
        _fail('motion_generation_source_unavailable')
    return rows, contents, sorted(omitted)


def _paths(rows):
    paths = [r['path'] for r in rows]
    if paths != sorted(paths) or len(paths) != len(set(p.casefold() for p in paths)):
        _fail()
    names = set(paths)
    if any(str(parent) in names for p in paths for parent in PurePosixPath(p).parents
           if str(parent) != '.'):
        _fail()


def _validate_files(rows):
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FILES:
        _fail()
    for row in rows:
        _keys(row, ('path', 'byte_length', 'sha256', 'git_blob_sha1'))
        _path(row['path'])
        if type(row['byte_length']) is not int or not 0 <= row['byte_length'] <= MAX_FILE_BYTES:
            _fail()
        _hash(row['sha256'], _SHA256)
        _hash(row['git_blob_sha1'], _SHA1)
    _paths(rows)
    if sum(r['byte_length'] for r in rows) > MAX_SOURCE_BYTES:
        _fail()


def _tree_hash(rows):
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FILES:
        _fail()
    tree = {}
    for row in rows:
        _keys(row, ('path', 'mode', 'blob_sha1'))
        _path(row['path'])
        _hash(row['blob_sha1'], _SHA1)
        if row['mode'] not in ('100644', '100755'):
            _fail()  # no symlinks, submodules or caller-selected object types
        node = tree
        for part in PurePosixPath(row['path']).parts[:-1]:
            node = node.setdefault(part, {})
            if type(node) is not dict:
                _fail()
        leaf = PurePosixPath(row['path']).name
        if leaf in node:
            _fail()
        node[leaf] = (row['mode'], row['blob_sha1'])
    _paths(rows)

    def digest(node):
        entries = []
        for name, item in node.items():
            is_tree = type(item) is dict
            mode, address = ('40000', digest(item)) if is_tree else item
            encoded = name.encode('utf-8')
            entries.append((encoded + (b'/' if is_tree else b''),
                            mode.encode('ascii') + b' ' + encoded + b'\0' + bytes.fromhex(address)))
        return _git_hash('tree', b''.join(payload for _, payload in sorted(entries)))
    return digest(tree)


def _commit(encoded, revision, tree):
    if type(encoded) is not str or len(encoded) > 65536:
        _fail()
    try:
        raw = b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        _fail()
    if (b64encode(raw).decode('ascii') != encoded or _git_hash('commit', raw) != revision or
            raw.split(b'\n', 1)[0] != b'tree ' + tree.encode('ascii')):
        _fail('motion_generation_frozen_commit_mismatch')
    return raw


def _committed_changes(upstream, loader):
    before, after = ({r['path']: r for r in rows} for rows in (upstream, loader))
    result = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            if path not in PATCH_NOTES:
                _fail('motion_generation_loader_changed')
            result.append(dict(path=path, upstream=before.get(path), loader=after.get(path),
                               declaration=PATCH_NOTES[path]))
    if {r['path'] for r in result} != set(PATCH_NOTES):
        _fail('motion_generation_loader_changed')
    return result


def _repository(value):
    _keys(value, ('url', 'upstream_revision', 'upstream_commit', 'upstream_tree',
                  'loader_revision', 'loader_commit', 'loader_tree', 'committed_local_changes'))
    if (value['url'] != UPSTREAM_URL or value['upstream_revision'] != UPSTREAM_REVISION or
            value['loader_revision'] != PINNED_REVISION):
        _fail('motion_generation_loader_changed')
    _commit(value['upstream_commit'], UPSTREAM_REVISION, _tree_hash(value['upstream_tree']))
    commit = _commit(value['loader_commit'], PINNED_REVISION, _tree_hash(value['loader_tree']))
    if [line for line in commit.split(b'\n\n', 1)[0].splitlines() if line.startswith(b'parent ')] != [
            b'parent ' + UPSTREAM_REVISION.encode('ascii')]:
        _fail()
    if value['committed_local_changes'] != _committed_changes(value['upstream_tree'], value['loader_tree']):
        _fail()


def _crlf_only(raw, expected_blob):
    if b'\0' in raw or b'\r\n' not in raw:
        return False
    try:
        raw.decode('utf-8')
    except UnicodeError:
        return False
    return _git_hash('blob', raw.replace(b'\r\n', b'\n')) == expected_blob


def _local_changes(files, contents, tree, declarations):
    before, after = ({r['path']: r for r in rows} for rows in (tree, files))
    result, used = [], set()
    for path in sorted(set(before) | set(after)):
        original, current = before.get(path), after.get(path)
        if original and current and original['blob_sha1'] == current['git_blob_sha1']:
            continue
        crlf = bool(original and current and _crlf_only(contents[path], original['blob_sha1']))
        kind = 'crlf-checkout' if crlf else ('added' if not original else 'deleted' if not current else 'modified')
        note = _CRLF_NOTE if crlf else declarations.get(path)
        if type(note) is not str or not note.strip() or len(note) > 1000:
            _fail('motion_generation_undeclared_source_patch')
        if not crlf:
            used.add(path)
        result.append(dict(path=path, kind=kind, base_git_blob_sha1=original['blob_sha1'] if original else None,
                           current=current, declaration=note))
    if set(declarations) != used:
        _fail('motion_generation_source_patch_declaration_mismatch')
    return result


def build_frozen_source_plan(root, *, git_executable, declared_patches=None):
    """Read the fixed root/source Git objects and worktree; never write or copy.

    Non-checkout byte changes require explicit path -> explanation declarations.
    Only the fixed upstream and local loader commits are accepted. Generated
    cache/egg-info files are omitted from the copy plan, not silently ignored by
    the installed runtime verifier. Do not ship the input .git directory.
    """
    root = _root(root)
    executable = Path(git_executable)
    if not executable.is_absolute():
        _fail('motion_generation_builder_git_invalid')
    read_real_file(executable, 64 << 20, 'Explicit build Git executable')
    _real_directory(root / 'source/.git')
    source = root / 'source'
    environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_OPTIONAL_LOCKS='0')

    def git(*arguments):
        result = subprocess.check_output([str(executable), '-c', f'safe.directory={source.as_posix()}',
                                          '-c', 'core.fsmonitor=false', '-C', str(source), *arguments],
                                         env=environment, stdin=subprocess.DEVNULL, timeout=30)
        if len(result) > MAX_RECEIPT_BYTES:
            _fail('motion_generation_frozen_source_too_large')
        return result

    if git('rev-parse', 'HEAD').strip().decode('ascii') != PINNED_REVISION:
        _fail('motion_generation_loader_changed')
    repository = dict(url=UPSTREAM_URL, upstream_revision=UPSTREAM_REVISION, loader_revision=PINNED_REVISION)
    for prefix, revision in (('upstream', UPSTREAM_REVISION), ('loader', PINNED_REVISION)):
        repository[prefix + '_commit'] = b64encode(git('cat-file', 'commit', revision)).decode('ascii')
        tree = []
        for entry in git('ls-tree', '-rz', '--full-tree', revision).split(b'\0'):
            if not entry:
                continue
            header, path = entry.split(b'\t', 1)
            mode, kind, address = header.decode('ascii').split(' ')
            if kind != 'blob':
                _fail()
            tree.append(dict(path=path.decode('utf-8'), mode=mode, blob_sha1=address))
        repository[prefix + '_tree'] = sorted(tree, key=lambda r: r['path'])
    repository['committed_local_changes'] = _committed_changes(repository['upstream_tree'], repository['loader_tree'])
    _repository(repository)
    files, contents, omitted = _inventory(root, building=True)
    declarations = {} if declared_patches is None else declared_patches
    if type(declarations) is not dict or any(_path(p) != p for p in declarations):
        _fail()
    receipt = dict(schema=SCHEMA, builder_profile=BUILDER, source_subdirectory='source',
                   repository=repository, files=files,
                   local_changes=_local_changes(files, contents, repository['loader_tree'], declarations),
                   source_inventory_sha256=sha256(canonical_bytes(files)).hexdigest())
    if len(canonical_bytes(receipt)) > MAX_RECEIPT_BYTES:
        _fail('motion_generation_frozen_source_too_large')
    return dict(schema='autospine.kimodo-frozen-source-plan/v1', receipt=receipt,
                receipt_filename=RECEIPT, receipt_sha256=sha256(canonical_bytes(receipt)).hexdigest(),
                copy_source_paths=[r['path'] for r in files], omitted_build_artifacts=omitted,
                model_inference_performed=False, runtime_ready=False)


def verify_frozen_source(root):
    """No Git, cache or revision-only trust: re-read the exact packaged source."""
    try:
        root = _root(root)
        raw = read_real_file(root / RECEIPT, MAX_RECEIPT_BYTES, 'Kimodo source receipt')
        value = strict_json_object(raw, 'Kimodo source receipt')
        _keys(value, ('schema', 'builder_profile', 'source_subdirectory', 'repository',
                      'files', 'local_changes', 'source_inventory_sha256'))
        if (value['schema'] != SCHEMA or value['builder_profile'] != BUILDER or
                value['source_subdirectory'] != 'source' or raw != canonical_bytes(value)):
            _fail()
        _repository(value['repository'])
        _validate_files(value['files'])
        if value['source_inventory_sha256'] != sha256(canonical_bytes(value['files'])).hexdigest():
            _fail()
        files, contents, _ = _inventory(root)
        if files != value['files']:
            _fail('motion_generation_frozen_source_changed')
        changes = value['local_changes']
        if type(changes) is not list:
            _fail()
        declarations = {}
        for change in changes:
            _keys(change, ('path', 'kind', 'base_git_blob_sha1', 'current', 'declaration'))
            if change['kind'] != 'crlf-checkout':
                if change['path'] in declarations:
                    _fail()
                declarations[_path(change['path'])] = change['declaration']
        if changes != _local_changes(files, contents, value['repository']['loader_tree'], declarations):
            _fail()
        return dict(repository_revision=PINNED_REVISION, upstream_revision=UPSTREAM_REVISION,
                    profile=BUILDER, receipt_sha256=sha256(raw).hexdigest(),
                    source_inventory_sha256=value['source_inventory_sha256'],
                    committed_local_changes=value['repository']['committed_local_changes'],
                    local_changes=changes, source_classification='pinned-local-loader-with-declared-worktree',
                    upstream_content_unchanged=False, publisher_signature_verified=False)
    except (OSError, UnicodeError, RuntimeError) as exc:
        raise ValueError('motion_generation_source_unavailable') from exc
    except ValueError as exc:
        if str(exc).startswith('motion_generation_'):
            raise
        raise ValueError('motion_generation_frozen_source_invalid') from exc
