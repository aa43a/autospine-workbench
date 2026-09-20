"""Compare explicit source projections; do not infer missing character artwork."""
from copy import deepcopy

from ..bvh_parser import parse_bvh
from ..resolved_project import canonical_sha256
from ..targets.character43.projection_diagnostics import bvh_series, kimodo_series, summarize
from .motion_intake_worker import VIEWS
from .motion_projection_review import source_context

PROFILE = 'full-source-front-side-projection-selection-v1'
LIMBS = {f'humanoid.{limb}.{part}.{side}' for limb in ('arm', 'leg')
         for part in ('upper', 'lower') for side in ('left', 'right')}


def compare(bundle, mapping, current_view):
    records = []
    bvh = parse_bvh(bundle.raw_bvh) if bundle.source_kind != 'kimodo_npz' else None
    for view, axes in VIEWS.items():
        candidate = deepcopy(mapping)
        candidate['basis'].update(zip(('screen_x', 'screen_y', 'depth'), axes))
        data = (kimodo_series(bundle.raw_npz, bundle.kimodo_source, candidate)
                if bvh is None else bvh_series(bvh, candidate))
        checked = summarize(*data)
        missing = sorted(LIMBS - {r['role'] for r in checked['records']})
        records.append(dict(view=view, basis=candidate['basis'], passed=checked['passed'] and not missing,
            missing_roles=missing,
            frame_count=len(checked['times']), minimum_visibility=min(r['minimum_visibility'] for r in checked['records']),
            failed_roles=[r['role'] for r in checked['records'] if not r['passed']],
            diagnostic=checked, map_sha256=canonical_sha256(candidate)))
    passing = [r['view'] for r in records if r['passed']]
    # Preserve a passing user view; no quality claim based on a partial score.
    selected = current_view if current_view in passing else next(iter(passing), None)
    return dict(profile=PROFILE, current_view=current_view, recommended_view=selected, records=records,
        status='current_view_passed' if selected == current_view else 'alternative_view_passed' if selected else 'no_supported_projection',
        authority='none', scope='complete_source_sampled_limb_projection_only',
        limitations=['target_geometry_contact_and_occlusion_require_new_candidate',
                     'projection_does_not_generate_side_or_back_artwork'])


def inspect(manager, job_id):
    job, bundle, mapping = source_context(manager, job_id)
    report = compare(bundle, mapping, job['view'])
    report.update(source_job_id=job_id, source_sha256=job['source_sha256'], motion_identity=job['result']['motion'])
    report['comparison_sha256'] = canonical_sha256(report)
    return report
