"""Display filenames from successful, source-bound upload journals, never aliases."""
import re
from .storage_io import directory, read_document


def upload_sources(state_root, project_ids):
    """Batch catalog lookup. No PSD parsing or mutable display-name inference."""
    wanted = set(project_ids)
    result = {project: dict(kind='unavailable' if project.startswith('imported-') else 'audit', file_names=[])
              for project in wanted}
    root = state_root/'jobs/psd-import-v1'
    if not root.exists():
        return result
    directory(root)
    for folder in sorted(root.iterdir()):
        if not re.fullmatch('import-[a-f0-9]{32}', folder.name):
            continue
        try:
            request = read_document(folder/'request.json')
            receipt = read_document(folder/'result.json')
            digest = request.get('source_sha256')
            name = request.get('name')
            if (not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)
                    or not isinstance(name, str) or not name.lower().endswith('.psd') or len(name) > 180
                    or any(ord(c) < 32 or c in '/\\:' for c in name)
                    or request.get('job_id') != folder.name or receipt.get('job_id') != folder.name
                    or receipt.get('status') != 'succeeded' or receipt.get('step') != 'complete'
                    or receipt.get('authority') != 'none' or receipt.get('project_id') != 'imported-'+digest):
                continue
            project = receipt['project_id']
            if project not in wanted:
                continue
            value = result[project]
            value.update(kind='uploaded_psd', source_sha256=digest)
            if name not in value['file_names']:
                value['file_names'].append(name)
        except (OSError, RuntimeError, ValueError, TypeError):
            # Unreadable or mismatched journals cannot establish a filename.
            continue
    for value in result.values():
        value['file_names'].sort()
    return result
