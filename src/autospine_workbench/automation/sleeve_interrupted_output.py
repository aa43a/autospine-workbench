"""Preserve unreceipted partial stage output separately before a fresh attempt."""
import os
from pathlib import Path
import re
from uuid import uuid4
from .storage_io import directory
from ..motion_instance_v3_staging_cleanup import is_alias


def preserve_partial(root, step, output):
    root=directory(root);output=Path(os.path.abspath(os.fspath(output)))
    if not re.fullmatch('[a-z]+(?:-[a-z]+)*',step):raise ValueError('sleeve_stage_invalid')
    try:parts=output.relative_to(root).parts
    except ValueError:raise ValueError('sleeve_stage_output_outside_run') from None
    if not parts or parts[0]!=step:raise ValueError('sleeve_stage_output_outside_run')
    if (root/'receipts'/(step+'.json')).exists():raise ValueError('sleeve_completed_output_preserved')
    if not output.exists():return None
    directory(output)
    if not any(output.iterdir()):return None
    for path in output.rglob('*'):
        if is_alias(path):raise ValueError('sleeve_output_alias')
        if path.is_dir():directory(path)
    destination=directory(root/'.interrupted',create=True)/(step+'-'+uuid4().hex)
    # Same-volume directory rename; no recursive deletion or following file links.
    os.rename(output,destination)
    directory(output,create=True)
    return destination
