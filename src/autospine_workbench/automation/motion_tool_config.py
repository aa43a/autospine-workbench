"""Server-owned tool locations; no executable path is accepted from upload clients."""
import json
import os
from pathlib import Path
import shutil


def blender_location(state_root):
    source, value = 'environment', os.environ.get('AUTOSPINE_BLENDER')
    if value is None:
        config = Path(state_root)/'config/motion-tools.json'
        if config.exists():
            source = 'state_config'
            try:
                if config.stat().st_size > 16384:
                    raise ValueError('oversized')
                document = json.loads(config.read_text(encoding='utf-8'))
                if not isinstance(document, dict) or set(document) != {'blender_executable'}:
                    raise ValueError('invalid fields')
                value = document['blender_executable']
            except (OSError, ValueError):
                return dict(path='', source=source, status='invalid_config')
        else:
            source, value = 'path', shutil.which('blender')
    # An explicit invalid setting must not select another executable silently.
    if not isinstance(value, str) or not value or '\0' in value:
        return dict(path='', source=source, status='not_configured')
    path = Path(value)
    if not path.is_absolute():
        return dict(path='', source=source, status='absolute_path_required')
    if not path.is_file():
        return dict(path='', source=source, status='executable_missing')
    return dict(path=str(path), source=source, status='configured')
