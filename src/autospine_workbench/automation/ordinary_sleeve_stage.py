"""Read one exact stage artifact, with project and content-address checks."""
from pathlib import Path
from ..benchmark.mesh_storage import read_mesh_report
from ..safe_input_files import read_real_file,strict_json_object
from ..resolved_project import canonical_sha256


def read_stage(root, project, state):
    paths=list((Path(root)/project).glob('*.json'))
    if len(paths)!=1:raise ValueError('sleeve_ordinary_stage_inventory')
    document=strict_json_object(read_real_file(paths[0],16<<20,'ordinary stage'),'ordinary stage')
    digest=canonical_sha256(document)
    if paths[0].stem!=digest or document.get('project_id')!=project:
        raise ValueError('sleeve_ordinary_stage_source')
    if read_mesh_report(state,'project-component-partitions',digest)!=document:
        raise ValueError('sleeve_ordinary_stage_changed')
    return document
