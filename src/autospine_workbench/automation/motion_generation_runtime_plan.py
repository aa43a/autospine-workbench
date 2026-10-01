"""Read-only required-payload plan; does not install, generate or claim readiness.

This closes the fixed generation code/model/license inputs. It is deliberately
not a distributable Python dependency bundle: the current venv has an external
base interpreter, and CUDA/import readiness needs a separate real probe. Large
weights can be size-planned or fully streamed; the report distinguishes them.
"""
from hashlib import sha256
import os
from pathlib import Path
import stat

from ..safe_input_files import read_real_file, strict_json_object
from .motion_generation_frozen_source import (
    _path, _real_directory, _root, build_frozen_source_plan,
)
from .storage_io import canonical_bytes

BASE_MANIFEST = 'modelscope.meta-llama-3-8b-instruct.manifest.json'
BASE_MANIFEST_SHA256 = '84525f8ab287d8863384959774c2226ce925df3dea2a423a0a6e3b6d5973f74e'
BASE_MODEL = 'text-encoders/modelscope/LLM-Research/Meta-Llama-3-8B-Instruct'
CHECKPOINT = 'checkpoints/Kimodo-SOMA-RP-v1.1'
MNTP = 'text-encoders/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp'
SUPERVISED = MNTP + '-supervised'
# Audited original inputs; neither filenames nor a newly supplied manifest can
# replace these identities. They are integrity pins, not redistribution grants.
FIXED_FILES = {
    'tools/modelscope_text_encoder.py': (13034, '755f4f6f70e0eba225419cd112e9a49a29e006f7a2b2a25d012d1eee25e4b2da'),
    CHECKPOINT + '/model.safetensors': (1133185036, 'ef0a0ca45a6089ab4532dde609785771ae3f38755b4ae6cf314b0213e07cd4a3'),
    CHECKPOINT + '/config.yaml': (675, '905664ad05779b0e28c391b85dc81c9de166418bd5f471ef605f75ab746ce391'),
    CHECKPOINT + '/LICENSE': (10229, '11ccdcb47db87ac30b63765b5e5154403026c4fbb52c19919d99d912ec454e19'),
    CHECKPOINT + '/stats/motion/body/mean.npy': (3040, 'd42f35f8bb7ef52fdec66ae29c5cf590bd038f4f1aabd2d560d1d0f78663ed6f'),
    CHECKPOINT + '/stats/motion/body/std.npy': (3040, '965bbad497726ef4e6c46b519827e2cbcb29f974214b25718d20a725b82279ed'),
    CHECKPOINT + '/stats/motion/global_root/mean.npy': (168, '6c110980f9a0386e57a8c186f8eac7f55dc05bade92f44c4b391450ada598da1'),
    CHECKPOINT + '/stats/motion/global_root/std.npy': (168, 'fb15aeed7143f5f0754611f0acf5fa5f55d1f6492a49c23e490fc62f7bf11fb0'),
    CHECKPOINT + '/stats/motion/local_root/mean.npy': (160, '4c36e8e33d6d51e6c8206ac796a52b7b3a4da7f0dc49ebdbb4f130178e3e9d31'),
    CHECKPOINT + '/stats/motion/local_root/std.npy': (160, '5f57b41f51ced7832cffa81702f6e04d8694e16475c184baec6c8be0e98c8dba'),
    MNTP + '/adapter_config.json': (794, '1d3bbf14142865885ea8d0dbc1fb261adf4f5d14ddbdc939efb47c4913037813'),
    MNTP + '/adapter_model.safetensors': (167829552, 'de9c8736618a13173c6a1623cdef1b75e86c69317f1073ae82cd516ac36a632d'),
    MNTP + '/attn_mask_utils.py': (11132, '86e463e1b82f27e3d3a8b9a1f76995dea3d8a7a41e5ece0431b27f084c143975'),
    MNTP + '/config.json': (781, '416c570276487324e49dca7c3d79e212b948d9cb2282fa734b1fa8014de041d1'),
    MNTP + '/modeling_llama_encoder.py': (2856, '05d27ca70e23ab92a793107fae1848589fd30046aaa6fea088e9fbe1f9073367'),
    MNTP + '/special_tokens_map.json': (335, '849070cae53bd45439e64ce5b1ddd650a66081b1bd47895c5a58939a05055579'),
    MNTP + '/tokenizer.json': (9085671, '52b583ee1699c6ca4468f70885bd5f96dd1f7517292362a67581038afc04f4d8'),
    MNTP + '/tokenizer_config.json': (51042, '0655c52e874137e4a455228155d982c4ea18419f461a10ceb57054995fec4223'),
    MNTP + '/README.md': (3315, 'a5e6ec837f09b94f5acd585e67c83fae843ed80769ec3e565b3a6b4b81ca085b'),
    SUPERVISED + '/adapter_config.json': (794, '2a1265e4a7829c16dad38a5175ec8ac41ea1e851654da5044ace2437615a58ba'),
    SUPERVISED + '/adapter_model.safetensors': (167829552, '53f8f94ebdf396667ba99dd96e78203edae27bbcdbd1cf5f12b611e1d916b225'),
    BASE_MODEL + '/LICENSE': (7801, '475211637354ce4c14b9c3dacccbefbaba735fe1b0db97d6c4fd11cd1356819f'),
    BASE_MODEL + '/USE_POLICY.md': (4696, '003513f595a20b7d63c609dfe80879531acb9caef6376fcc109bf0827471f3d1'),
}


def _metadata(root, relative):
    relative = _path(relative)
    path = root / relative
    for parent in path.parents:
        _real_directory(parent)
        if parent == root:
            break
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or
            getattr(info, 'st_file_attributes', 0) & 0x400):
        raise ValueError('motion_generation_runtime_payload_unsafe')
    return path, info


def _payload(root, relative, size, expected, *, verify):
    path, before = _metadata(root, relative)
    if before.st_size != size:
        raise ValueError('motion_generation_runtime_payload_changed')
    if verify:
        digest = sha256()
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, size):
                raise ValueError('motion_generation_runtime_payload_changed')
            for chunk in iter(lambda: stream.read(8 << 20), b''):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
        if ((opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or
                digest.hexdigest() != expected):
            raise ValueError('motion_generation_runtime_payload_changed')
    return dict(path=relative, byte_length=size, sha256=expected, bytes_verified=verify)


def build_runtime_integrity_plan(root, *, git_executable, declared_patches=None,
                                 verify_weight_bytes=False):
    """Validate the complete required code/model copy plan without writing.

    The default hashes code, manifests, small model inputs and notices, but only
    validates large weight sizes. True additionally streams every model weight.
    Both forms leave runtime_ready false: no imports/CUDA/inference occurred.
    """
    if type(verify_weight_bytes) is not bool:
        raise ValueError('motion_generation_runtime_plan_invalid')
    root = _root(root)
    source = build_frozen_source_plan(root, git_executable=git_executable,
                                     declared_patches=declared_patches)
    raw = read_real_file(root / BASE_MANIFEST, 64 << 10, 'Fixed ModelScope manifest')
    if sha256(raw).hexdigest() != BASE_MANIFEST_SHA256:
        raise ValueError('motion_generation_text_manifest_changed')
    manifest = strict_json_object(raw, 'Fixed ModelScope manifest')
    if (manifest.get('schema_version') != 'modelscope-file-manifest/v1' or
            manifest.get('model_id') != 'LLM-Research/Meta-Llama-3-8B-Instruct'):
        raise ValueError('motion_generation_runtime_plan_invalid')
    expected = dict(FIXED_FILES)
    for entry in manifest['files']:
        relative = BASE_MODEL + '/' + _path(entry['path'])
        if relative in expected:
            raise ValueError('motion_generation_runtime_plan_invalid')
        expected[relative] = (entry['bytes'], entry['sha256'])
    rows = [dict(path=BASE_MANIFEST, byte_length=len(raw), sha256=BASE_MANIFEST_SHA256,
                 bytes_verified=True)]
    for relative, (size, digest) in sorted(expected.items()):
        rows.append(_payload(root, relative, size, digest,
                             verify=verify_weight_bytes or not relative.endswith('.safetensors')))
    index = strict_json_object(read_real_file(root / BASE_MODEL / 'model.safetensors.index.json',
                                             1 << 20, 'Model shard index'), 'Model shard index')
    if set(index.get('weight_map', {}).values()) != {
            r['path'].rsplit('/', 1)[1] for r in rows
            if r['path'].startswith(BASE_MODEL + '/') and r['path'].endswith('.safetensors')}:
        raise ValueError('motion_generation_text_shard_closure_changed')
    python, _ = _metadata(root, '.venv/Scripts/python.exe')
    config = read_real_file(root / '.venv/pyvenv.cfg', 16 << 10, 'Existing Kimodo venv configuration')
    fields = dict(line.split('=', 1) for line in config.decode('utf-8').splitlines() if '=' in line)
    base = Path(fields.get('home ', fields.get('home', '')).strip())
    external = not base.is_absolute() or not base.is_relative_to(root)
    blockers = ['python_dependency_imports_not_checked', 'cuda_not_checked', 'model_generation_not_performed']
    if external:
        blockers.insert(0, 'existing_venv_requires_external_base_python')
    if not verify_weight_bytes:
        blockers.insert(0, 'large_model_weight_hashes_not_checked')
    return dict(schema='autospine.kimodo-runtime-integrity-plan/v1',
                scope='required-generation-payload-not-complete-python-bundle', source_plan=source,
                payload=sorted(rows, key=lambda r: r['path']),
                payload_inventory_sha256=sha256(canonical_bytes(sorted(rows, key=lambda r: r['path']))).hexdigest(),
                all_required_model_bytes_verified=verify_weight_bytes,
                interpreter=dict(relative_path=python.relative_to(root).as_posix(),
                                 external_base_required=external, imports_checked=False),
                cuda_status='not_checked', runtime_ready=False, blockers=blockers,
                licenses=dict(source='source/LICENSE', checkpoint=CHECKPOINT + '/LICENSE',
                              base_model=BASE_MODEL + '/LICENSE', base_use_policy=BASE_MODEL + '/USE_POLICY.md',
                              adapter_license_declaration=MNTP + '/README.md',
                              redistribution_authorized_by_this_plan=False),
                source_or_model_written=False, model_inference_performed=False)
