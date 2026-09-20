"""Per-job derived text adapters; shared downloaded originals remain read-only."""
import importlib.util
import shutil
import sys

from .motion_generation_provenance import identity
from .storage_io import canonical_bytes, read_document


def verify(folder):
    layout = folder / 'text-encoders'
    current = {p.relative_to(layout).as_posix(): identity(p) for p in layout.rglob('*') if p.is_file()}
    if current != read_document(folder / 'text-encoder-files.json'):
        raise ValueError('motion_generation_environment_changed')


def prepare(runtime, folder):
    path = runtime / 'tools/modelscope_text_encoder.py'
    spec = importlib.util.spec_from_file_location('_autospine_kimodo_preparation', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest = runtime / 'modelscope.meta-llama-3-8b-instruct.manifest.json'
    model = runtime / module.MODEL_RELATIVE_PATH
    _, digest = module.verify_modelscope_snapshot(model, manifest)
    layout = folder / 'text-encoders'
    adapter = layout / 'McGill-NLP' / module.MNTP_ADAPTER_NAME
    module.prepare_mntp_overlay(source_dir=runtime / module.MNTP_SOURCE_RELATIVE_PATH,
                               model_dir=model, overlay_dir=adapter, manifest_sha256=digest)
    supervised = layout / 'McGill-NLP' / module.SUPERVISED_ADAPTER_NAME
    supervised.mkdir()
    for name in ('adapter_config.json', 'adapter_model.safetensors'):
        shutil.copyfile(runtime / 'text-encoders' / module.SUPERVISED_ADAPTER_NAME / name, supervised / name)
    (folder / 'modelscope-base-manifest.json').write_bytes(manifest.read_bytes())
    (folder / 'text-encoder-overlay-manifest.json').write_bytes((adapter / module.OVERLAY_MANIFEST_NAME).read_bytes())
    inventory = {p.relative_to(layout).as_posix(): identity(p) for p in layout.rglob('*') if p.is_file()}
    (folder / 'text-encoder-files.json').write_bytes(canonical_bytes(inventory))
    return layout
