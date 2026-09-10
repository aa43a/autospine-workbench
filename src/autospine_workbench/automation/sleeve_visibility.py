"""Append-only candidate visibility; immutable workflow evidence stays untouched."""
from .pipeline_run import PipelineRunError
from .storage_io import directory, publish_document, read_document


def read(root):
    folder = root / 'visibility'
    if not folder.exists():
        return dict(revision=0, withdrawn=False)
    directory(folder)
    paths = sorted(folder.glob('*.json'))
    state = dict(revision=0, withdrawn=False)
    for revision, path in enumerate(paths, 1):
        if path.name != f'{revision:08d}.json':
            raise PipelineRunError('sleeve_visibility_invalid')
        state = read_document(path)
        if (set(state) != {'revision', 'withdrawn'} or type(state['revision']) is not int
                or state['revision'] != revision or type(state['withdrawn']) is not bool):
            raise PipelineRunError('sleeve_visibility_invalid')
    return state


def write(root, expected_revision, withdrawn):
    state = read(root)
    if state['revision'] != expected_revision:
        # A repeated request may replay exactly its immediately committed change.
        if state == dict(revision=expected_revision + 1, withdrawn=withdrawn):
            return
        raise PipelineRunError('sleeve_visibility_conflict')
    if state['withdrawn'] == withdrawn:
        return
    folder = directory(root / 'visibility', create=True)
    value = dict(revision=expected_revision + 1, withdrawn=withdrawn)
    if not publish_document(folder / f'{value["revision"]:08d}.json', value, staging=root / '.staging'):
        if read(root) != value:
            raise PipelineRunError('sleeve_visibility_conflict')


def view(job, root):
    state = read(root)
    job.update(candidate_withdrawn=state['withdrawn'], visibility_revision=state['revision'])
    if state['withdrawn']:
        job.pop('result', None)
    return job
