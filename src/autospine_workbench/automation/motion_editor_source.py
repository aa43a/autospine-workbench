"""Read-only verified full source observations for the interactive motion editor."""
from ..motion_roles import nearest_mapped_parent_role
from ..resolved_project import canonical_sha256
from ..targets.character43.oblique_source import extract, _basis
from ..targets.character43.source_hip_centers import extract as hip_centers
from ..targets.character43.motionir_candidate import ROLES
from .motion_projection_review import source_context
from .pipeline_run import PipelineRunError


def build(bundle, mapping):
    vectors, roots, reference = extract(bundle)
    centers, hip_reference = hip_centers(bundle)
    tracks=[t for t in bundle.motion['tracks'] if t['property']=='rotation']
    ticks=[k['tick'] for k in tracks[0]['keys']]
    if (hip_reference!=reference or not 2<=len(ticks)<=768
            or any([k['tick'] for k in t['keys']]!=ticks for t in tracks)):
        raise ValueError('motion_editor_source_samples_invalid')
    times=[t/bundle.motion['ticks_per_second'] for t in ticks]
    if bundle.source_kind=='bvh':
        from ..bvh_parser import parse_bvh
        from ..bvh_fk import _world_matrices, _origin
        source=parse_bvh(bundle.raw_bvh)
        names=[j.name for j in source.joints];parents=[j.parent_index for j in source.joints]
        positions=[[_origin(m) for m in _world_matrices(source,frame)] for frame in source.frames]
    else:
        from ..kimodo_npz_reader import decode_kimodo_npz
        from ..kimodo_npz_consistency import validate_kimodo_consistency
        from ..kimodo_soma77 import SOMA77_JOINT_NAMES, SOMA77_PARENT_INDICES
        source=validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz,bundle.kimodo_source),bundle.kimodo_source)
        names=list(SOMA77_JOINT_NAMES);parents=list(SOMA77_PARENT_INDICES);positions=source.positions
    if len(positions)!=len(times):raise ValueError('motion_editor_source_samples_invalid')
    def point(p):
        x,y,z=_basis(p,mapping['basis']);return [x,-y,z]
    preview=dict(schema='autospine.source-motion-preview/v1',view='front',names=names,parents=parents,
        frames=[dict(time=t,frame=i,joints=[point(p) for p in positions[i]]) for i,t in enumerate(times)],
        scope='full_source_samples_in_declared_camera_basis')
    return dict(schema='autospine.motion-editor-source/v1',vectors=vectors,roots=roots,hip_centers=centers,
        times=times,duration=bundle.motion['duration_ticks']/bundle.motion['ticks_per_second'],reference=reference,
        role_bones=dict(ROLES),role_parents={r:nearest_mapped_parent_role(r,vectors) for r in vectors},
        precision=5 if bundle.source_kind=='kimodo_npz' else 12,preview=preview,
        scope='raw_camera_pose_not_corrected_or_quality_accepted',authority='none')


def read(manager,job_id):
    job,bundle,mapping=source_context(manager,job_id)
    try: value=build(bundle,mapping)
    except ValueError as exc:raise PipelineRunError(str(exc)) from exc
    value.update(source_job_id=job_id,motion_identity=job['result']['motion'],source_sha256=job['source_sha256'])
    value['snapshot_sha256']=canonical_sha256(value)
    return value
