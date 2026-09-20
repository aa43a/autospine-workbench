"""Record current bytes and pinned loader identity, never copy an old run's receipt."""
from hashlib import sha256
from pathlib import Path
import subprocess

from .motion_generation_jobs import MODEL
from .storage_io import canonical_bytes

REVISION = 'c503c77aa877f4e4469402ae197bb0e5739bbedd'
CHECKPOINT_REVISION = '6c9233af1180b8151e3c4703477104af5dce9dd5'
WEIGHTS = 'ef0a0ca45a6089ab4532dde609785771ae3f38755b4ae6cf314b0213e07cd4a3'


def identity(path):
    digest = sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(4 << 20), b''):
            digest.update(chunk)
    return dict(byte_length=path.stat().st_size, sha256=digest.hexdigest())


def code_revision(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root / 'source'), *args],
                                       timeout=30, text=True).strip()
    revision = git('rev-parse', 'HEAD')
    if revision != REVISION or git('status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('motion_generation_loader_changed')
    return revision


def inspect(root):
    revision = code_revision(root)
    base = root / 'checkpoints' / MODEL
    files = ['config.yaml', 'model.safetensors']
    files += [f'stats/motion/{part}/{name}.npy' for part in ('body', 'global_root', 'local_root')
              for name in ('mean', 'std')]
    checkpoint = {name: identity(base / name) for name in files}
    if (checkpoint['model.safetensors']['sha256'] != WEIGHTS or
            checkpoint['config.yaml']['sha256'] != '905664ad05779b0e28c391b85dc81c9de166418bd5f471ef605f75ab746ce391'):
        raise ValueError('motion_generation_checkpoint_changed')
    adapters = {}
    layout = root / 'text-encoders'
    for suffix in ('', '-supervised'):
        name = 'LLM2Vec-Meta-Llama-3-8B-Instruct-mntp' + suffix
        adapters[name] = {file: identity(layout / name / file)
                          for file in ('adapter_config.json', 'adapter_model.safetensors')}
    return dict(schema='autospine.kimodo-generation-environment/v1', model=MODEL,
                repository_revision=revision, checkpoint_revision=CHECKPOINT_REVISION,
                checkpoint=checkpoint, adapters=adapters,
                runner=identity(Path(__file__).with_name('motion_generation_worker.py')),
                layout_builder=identity(Path(__file__).with_name('motion_generation_layout.py')),
                preparation=identity(root / 'tools/modelscope_text_encoder.py'),
                base_manifest=identity(root / 'modelscope.meta-llama-3-8b-instruct.manifest.json'),
                postprocess=False, text_encoder_device='cpu', offline=True)


def producer(environment, generation):
    return dict(status='recorded', implementation='nv-tlabs/kimodo',
                repository_revision=environment['repository_revision'], model_id=MODEL,
                checkpoint_revision=CHECKPOINT_REVISION,
                checkpoint_manifest_sha256=sha256(canonical_bytes(environment)).hexdigest(),
                generation_request_sha256=sha256(canonical_bytes(generation)).hexdigest(),
                seed=generation['seed'], sample_index=0)
