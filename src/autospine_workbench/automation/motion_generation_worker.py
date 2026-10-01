"""Offline Kimodo subprocess bridge; only a new job directory receives outputs."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

from ..safe_input_files import read_real_file
from .motion_generation_jobs import MODEL, options
from .motion_generation_provenance import inspect, producer
from .motion_generation_layout import prepare, verify
from .motion_intake_process import progress
from .motion_kimodo_intake import compile_source
from .storage_io import canonical_bytes, read_document

KIMODO_ISOLATED_LAUNCH_PROFILE = 'isolated-no-bytecode-v1'
KIMODO_ISOLATED_FLAGS = ('-I', '-B', '-X', 'utf8')


def kimodo_command(python, *arguments):
    # These flags act before Python executes site or a user .pth hook. The
    # embedded interpreter's late _pth isolation alone is insufficient on 3.12.
    return [python, *KIMODO_ISOLATED_FLAGS, *arguments]


def execute(folder, state_root, runtime):
    request = read_document(folder / 'request.json')
    selected = options(request['generation'])
    progress(folder, 'verify_generator')
    environment = inspect(runtime)
    (folder / 'generation-environment.json').write_bytes(canonical_bytes(environment))
    # Unique immutable output: canceled/failed work is retained, retries get a new ID.
    output = folder / 'generated'
    if output.exists():
        raise ValueError('motion_generation_output_exists')
    config = dict(schema_version='kimodo-text-generation-request/v1', job_id=request['job_id'],
                  model=MODEL, prompt=selected['prompt'], duration_seconds=selected['duration_seconds'],
                  seed=selected['seed'], sample_index=0, num_samples=1,
                  diffusion_steps=selected['diffusion_steps'], num_transition_frames=5,
                  output_stem='generated/motion',
                  export=dict(bvh=False, bvh_standard_tpose=False, save_example_dir=False), postprocess=False)
    config_path = folder / 'generation-request.json'
    config_path.write_bytes(canonical_bytes(config))
    progress(folder, 'verify_text_encoder')
    layout = prepare(runtime, folder)
    output.mkdir()
    env = dict(os.environ, PYTHONPATH=str(runtime / 'source'), HF_HOME=str(folder / 'model-cache'),
               HF_HUB_CACHE=str(folder / 'model-cache/hub'),
               HF_ASSETS_CACHE=str(folder / 'model-cache/assets'),
               HF_MODULES_CACHE=str(folder / 'model-cache/modules'),
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONUTF8='1', TOKENIZERS_PARALLELISM='false',
               CHECKPOINT_DIR=str(runtime / 'checkpoints'), TEXT_ENCODERS_DIR=str(layout),
               TEXT_ENCODER_MODE='local', TEXT_ENCODER_DEVICE='cpu')
    python = str(runtime / '.venv/Scripts/python.exe')
    device = subprocess.run(kimodo_command(python, '-c', 'import torch; assert torch.cuda.is_available(), "CUDA unavailable"'),
                            env=env, capture_output=True, timeout=60)
    if device.returncode:
        raise ValueError('motion_generation_cuda_unavailable')
    command = kimodo_command(python, '-u', '-m', 'kimodo.scripts.generate', selected['prompt'], '--model', MODEL,
               '--duration', str(selected['duration_seconds']), '--num_samples', '1',
               '--diffusion_steps', str(selected['diffusion_steps']), '--num_transition_frames', '5',
               '--output', str(output / 'motion'), '--seed', str(selected['seed']), '--no-postprocess')
    progress(folder, 'generate_motion')
    # Child inherits the worker's process tree; the manager owns cancellation/timeout.
    with subprocess.Popen(command, cwd=runtime, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          encoding='utf-8', errors='replace') as child:
        with (folder / 'generation.log').open('w', encoding='utf-8') as log:
            for line in child.stdout:
                log.write(line)
                log.flush()
        if child.wait():
            raise ValueError('motion_generation_failed')
    progress(folder, 'verify_generation')
    # Recheck code, weights, runner and adapter bytes before recording the output.
    if inspect(runtime) != environment:
        raise ValueError('motion_generation_environment_changed')
    verify(folder)
    raw = read_real_file(output / 'motion.npz', 64 << 20, 'generated motion')
    with (folder / 'source.npz').open('xb') as target:
        target.write(raw)
    result = compile_source(raw, request, folder, state_root, producer=producer(environment, config))
    result.update(source_sha256=sha256(raw).hexdigest(), byte_length=len(raw),
                  generation=dict(parameters=selected, model=MODEL, postprocess=False,
                                  environment_sha256=sha256(canonical_bytes(environment)).hexdigest(),
                                  request_sha256=sha256(canonical_bytes(config)).hexdigest()))
    (folder / 'worker-result.json').write_bytes(canonical_bytes(result))


if __name__ == '__main__':
    try:
        execute(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        message = str(exc)
        print(json.dumps(dict(reason_code=message if message.startswith('motion_') else 'motion_generation_failed')))
        sys.exit(1)
