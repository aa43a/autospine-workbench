"""Immutable pre-layer-edit checkpoints. Final QA and Runtime are never cached."""
from hashlib import sha256
import json
import os
from pathlib import Path

from .storage_io import canonical_bytes, directory, publish_document, read_document
from ..safe_input_files import read_real_file
from ..staging_file import create_staging_file

LIMIT = 128 * 1024 * 1024
PROFILE = 'motion-pre-layer-checkpoint-v1'


def algorithm_digest():
    root = Path(__file__).resolve().parents[1]
    return sha256(canonical_bytes({p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(root.rglob('*.py'))})).hexdigest()


def identity(request, algorithm):
    # All other request fields remain dependencies, including clip, camera and policies.
    source = {k: v for k, v in request.items()
              if k not in ('job_id', 'layer_edits', 'layer_edit_receipt')}
    return sha256(canonical_bytes(dict(profile=PROFILE, algorithm=algorithm, request=source))).hexdigest()


class PreparationCache:
    def __init__(self, state_root, request):
        self.key = identity(request, algorithm_digest())
        self.root = Path(state_root) / 'motion-preparation-cache'
        self.status = 'miss'

    def load(self):
        if not self.root.exists():
            return None
        try:
            directory(self.root)
            manifest = read_document(self.root / (self.key + '.json'))
            if manifest['key'] != self.key or manifest['profile'] != PROFILE:
                raise ValueError('checkpoint_identity')
            digest = manifest['payload_sha256']
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('checkpoint_digest')
            raw = read_real_file(self.root / (digest + '.payload'), LIMIT, 'motion checkpoint')
            if sha256(raw).hexdigest() != digest:
                raise ValueError('checkpoint_corrupt')
            state = json.loads(raw)
            if not isinstance(state, dict) or canonical_bytes(state) != raw:
                raise ValueError('checkpoint_format')
            self.status = 'hit'
            return state
        except Exception:
            # An unavailable or damaged optimization must not bypass a full build.
            self.status = 'unavailable'
            return None

    def save(self, state):
        try:
            raw = canonical_bytes(state)
            if len(raw) > LIMIT:
                self.status = 'too_large'
                return
            directory(self.root, create=True)
            digest = sha256(raw).hexdigest()
            descriptor, name = create_staging_file(self.root)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, 'wb') as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, self.root / (digest + '.payload'))
                except FileExistsError:
                    pass
                publish_document(self.root / (self.key + '.json'),
                                 dict(profile=PROFILE, key=self.key, payload_sha256=digest),
                                 staging=self.root)
            finally:
                temporary.unlink(missing_ok=True)
        except Exception:
            self.status = 'unavailable'

    def report(self):
        return dict(status=self.status, key=self.key, scope='pre_layer_edit_only',
                    final_checks='rerun', runtime='rerun')
