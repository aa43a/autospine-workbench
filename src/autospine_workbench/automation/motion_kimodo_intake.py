"""Explicit SOMA77 interpretation and real compiler, without invented provenance."""
from dataclasses import asdict
from fractions import Fraction
from hashlib import sha256
import math

from ..kimodo_npz_reader import inspect_kimodo_npz_profile, decode_kimodo_npz
from ..kimodo_npz_consistency import validate_kimodo_consistency
from ..kimodo_npz_source import COORDINATE_SYSTEM
from ..kimodo_soma77 import (PROFILE_ID, SOMA77_DEFINITION_SHA256,
                             SOMA77_JOINT_NAMES, SOMA77_PARENT_INDICES, SOMA77_INDEX_BY_NAME)
from ..motion_kimodo_commands import compile_kimodo_motion_bundle
from .pipeline_run import PipelineRunError
from .storage_io import canonical_bytes
from .motion_intake_process import progress


def options(profile, fps):
    if profile != PROFILE_ID or not isinstance(fps, str) or len(fps) > 16:
        raise PipelineRunError('motion_npz_profile_required')
    try:
        rate = Fraction(fps)
        if not 1 <= rate <= 240 or max(rate.numerator, rate.denominator) > 1_000_000:
            raise ValueError()
    except (ValueError, ZeroDivisionError):
        raise PipelineRunError('motion_npz_fps_invalid') from None
    return dict(profile=profile, fps=str(rate))


def sidecar(raw, settings):
    frames, inventory, count = inspect_kimodo_npz_profile(raw)
    rate = Fraction(settings['fps'])
    return dict(format='autospine-kimodo-npz-source', format_version=1,
        source_id='external.' + sha256(raw).hexdigest()[:16],
        raw_npz=dict(sha256=sha256(raw).hexdigest(), byte_length=len(raw), frame_count=frames,
                     frames_per_second=dict(numerator=rate.numerator, denominator=rate.denominator)),
        producer=dict(status='unavailable', implementation='nv-tlabs/kimodo', reason_code='external_export'),
        skeleton=dict(profile_id=PROFILE_ID, joint_count=77, definition_sha256=SOMA77_DEFINITION_SHA256,
                      definition_scope='joint_names_and_parents', rest_geometry_policy='source_frame0_unverified'),
        coordinate_system=dict(COORDINATE_SYSTEM),
        array_profile=dict(inventory=inventory, float_dtype='<f4', contact_dtype='|b1',
            contact_layout=('left-heel-toe-right-heel-toe-v1' if count == 4
                            else 'left-heel-toe-toe_end-right-heel-toe-toe_end-v1')))


def mapping(source, positions, view):
    from .motion_intake_worker import VIEWS
    pairs = [('humanoid.root', 'Hips', 'Spine1'), ('humanoid.spine.lower', 'Spine1', 'Spine2'),
             ('humanoid.spine.upper', 'Spine2', 'Chest'), ('humanoid.neck', 'Neck1', 'Neck2'),
             ('humanoid.head', 'Head', 'HeadEnd')]
    legs = []
    for side, prefix in [('left', 'Left'), ('right', 'Right')]:
        for role, a, b in [('clavicle', 'Shoulder', 'Arm'), ('arm.upper', 'Arm', 'ForeArm'),
                           ('arm.lower', 'ForeArm', 'Hand'), ('leg.upper', 'Leg', 'Shin'),
                           ('leg.lower', 'Shin', 'Foot')]:
            pairs.append(('humanoid.' + role + '.' + side, prefix + a, prefix + b))
            if role.startswith('leg.'):
                legs.append(math.dist(positions[SOMA77_INDEX_BY_NAME[prefix+a]],
                                      positions[SOMA77_INDEX_BY_NAME[prefix+b]]))
    layout = source['array_profile']['contact_layout']
    points = ('heel', 'toe', 'toe_end') if 'toe_end' in layout else ('heel', 'toe')
    channels = [dict(index=i, limb='leg.'+side, point=p) for i, (side, p) in
                enumerate((s, p) for s in ('left', 'right') for p in points)]
    axes = VIEWS[view]
    return dict(format='autospine-kimodo-npz-map', format_version=1,
        map_id='kimodo.soma77.'+view+'-v1', clip=dict(clip_id=source['source_id']+'.'+view, loop=False),
        basis=dict(screen_x=axes[0], screen_y=axes[1], depth=axes[2],
                   rotation_convention='validated_matrix_fk_projected_segment'),
        root=dict(joint_name='Hips', position_source='root_positions', reference_length_meters=sum(legs)/2,
                  translation_policy='projected_frame0_delta_normalized_reference_length', baseline_policy='source_frame0'),
        bones=[dict(role=r, joint_name=a, aim_joint_name=b,
                    rotation_policy='projected_setup_local_delta_from_validated_fk') for r, a, b in pairs],
        contact=dict(enabled=True, source='foot_contacts', layout=layout, channels=channels,
                     reduction_policy='any_true_per_limb', mode='annotation_only', interval='half_open'))


def compile_source(raw, request, folder, state_root, *, producer=None):
    settings = options(**request.get('npz_options', {}))
    progress(folder, 'inspect_npz')
    source = sidecar(raw, settings)
    if producer is not None:
        source['producer'] = producer
    snapshot = decode_kimodo_npz(raw, source)
    validated = validate_kimodo_consistency(snapshot, source)
    fps = float(Fraction(settings['fps']))
    indices = sorted({round(i*(snapshot.frame_count-1)/min(239, snapshot.frame_count-1))
                      for i in range(min(240, snapshot.frame_count))})
    preview = dict(schema='autospine.source-motion-preview/v1', names=SOMA77_JOINT_NAMES,
                   parents=SOMA77_PARENT_INDICES, view=request['view'],
                   frames=[dict(time=i/fps, frame=i, joints=validated.positions[i]) for i in indices],
                   scope='matrix_validated_source_joint_samples_not_character_animation')
    preview_raw = canonical_bytes(preview)
    (folder/'preview.json').write_bytes(preview_raw)
    (folder/'sidecar.json').write_bytes(canonical_bytes(source))
    selected = mapping(source, validated.positions[0], request['view'])
    (folder/'map.json').write_bytes(canonical_bytes(selected))
    result = dict(frame_count=snapshot.frame_count, joint_count=77, fps=fps,
                  duration_seconds=(snapshot.frame_count-1)/fps, preview_sha256=sha256(preview_raw).hexdigest(),
                  projection=request['view'], loop=False, contact_status='source_labels_annotation_only',
                  producer_status='recorded' if producer is not None else 'unavailable_external_export', interpretation=settings,
                  target_runtime_status='not_evaluated', character_animation_status='not_built',
                  consistency=dict(max_position_error_meters=validated.max_position_error_meters,
                                   max_global_matrix_error=validated.max_global_matrix_error))
    progress(folder, 'compile_motion')
    try:
        compiled = compile_kimodo_motion_bundle(state_root, folder/'source.npz', folder/'sidecar.json', folder/'map.json')
    except (ValueError, RuntimeError) as exc:
        return dict(result, motion_status='needs_mapping', reason_code='motion_projection_or_mapping_unsupported',
                    diagnostic=str(exc)[:500])
    identity = asdict(compiled)
    identity.pop('path', None)
    return dict(result, motion_status='compiled', motion=identity,
                reference_length_source_units=selected['root']['reference_length_meters'],
                reference_policy='mean_frame_zero_leg_segment_lengths')
