"""Pure fresh-project sleeve grids from current registered inputs.

The caller loads AnimatedInputs, checks assert_current before/after publication,
and persists every auxiliary document. Geometry proposals grant no approval.
"""
from copy import deepcopy
import re
import unicodedata

from ..asset.planning.component_partitions import build as partition
from ..asset.planning.component_ownership import template as ownership_template
from ..asset.planning.component_suggestions import build as suggest
from ..asset.planning.component_candidate_draft import prefill
from ..asset.planning.component_mesh import build as build_mesh
from ..asset.planning.sleeve_regions import build as regions, template
from ..resolved_project import canonical_sha256


class SleeveOnboardingError(ValueError):
    def __init__(self, reason_code, blockers=()):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.blockers = list(blockers)


def _arm_options(binding):
    result = []
    for option in binding.get('options', []):
        ids = option['bone_ids']
        # Restrict automatic component candidates to complete arm chains.
        # Partial rigid options must not outrank a full three-bone option.
        for suffix in ('l', 'r'):
            expected = [f'{name}_{suffix}' for name in ('upperarm', 'forearm', 'hand')]
            if option.get('mode') == 'mesh_chain' and all(b in ids for b in expected):
                result.append(dict(id=f'sleeve:{suffix}', mode='mesh_chain', bone_ids=expected))
    unique = {tuple(r['bone_ids']): r for r in result}
    return list(unique.values())


def _semantic(layer):
    semantic = layer.get('semantic')
    if semantic:
        return semantic if semantic in ('body.arm', 'wear.sleeve') else None
    name = ' '.join(unicodedata.normalize('NFKC', layer['name']).lower().split())
    base = re.sub(r'-[lr]$', '', name)
    return {'handwear': 'body.arm', 'arm': 'body.arm', 'sleeve': 'wear.sleeve'}.get(base)


def build_inputs(inputs, project_id):
    """Return source, regions, pending triangle draft, and replay auxiliaries.

    Auxiliary ``blockers`` includes pending components and failed geometry; these
    are retained in source.records even when other regions can be edited.
    An entirely unavailable grid raises SleeveOnboardingError with those details.
    """
    skeleton = inputs.skeleton
    if skeleton.get('status') != 'candidate_requires_review' or not skeleton.get('bones'):
        raise SleeveOnboardingError('sleeve_source_joints_unreviewed',
                                   skeleton.get('reason_codes', []))
    bindings = {b['layer_id']: b for b in inputs.bindings['bindings']}
    selected, options, blockers = [], [], []
    for original in inputs.candidate['layers']:
        semantic = _semantic(original)
        if semantic is None:
            continue
        layer = deepcopy(original)
        layer['semantic'] = semantic
        binding = bindings.get(layer['layer_id'], {})
        allowed = _arm_options(binding)
        if not allowed:
            blockers.append(dict(layer_id=layer['layer_id'], reason_code='sleeve_arm_chain_required'))
        selected.append(layer)
        options.append(dict(layer_id=layer['layer_id'], options=allowed))
    if not selected:
        raise SleeveOnboardingError('sleeve_no_eligible_layers')
    analysis_bindings = dict(bindings=options)
    # This is a distinct analysis plan, not an existing rig-plan identity.
    plan = dict(schema='autospine.sleeve-onboarding-plan/v1', profile='sleeve-onboarding-v1',
                project_id=project_id, source_addresses=deepcopy(inputs.source_addresses),
                candidate_sha256=canonical_sha256(inputs.candidate),
                skeleton_sha256=canonical_sha256(skeleton),
                bindings_sha256=canonical_sha256(inputs.bindings),
                analysis_bindings_sha256=canonical_sha256(analysis_bindings),
                binding_draft_sha256=canonical_sha256(inputs.draft),
                layers=[dict(layer_id=r['layer_id'], semantic=r['semantic'],
                             evidence='source_semantic' if original.get('semantic') else 'normalized_name_candidate')
                        for r in selected for original in inputs.candidate['layers']
                        if original['layer_id'] == r['layer_id']],
                authority='none', production_authorized=False, human_reviewed=False)
    plan_sha = canonical_sha256(plan)
    entries, documents = [], []
    for layer in selected:
        try:
            raw = inputs.images[layer['layer_id']]
            candidate = partition(layer, raw)
        except ValueError as exc:
            raise SleeveOnboardingError('sleeve_partition_unavailable',
                [dict(layer_id=layer['layer_id'], reason_code=str(exc))]) from exc
        doc = dict(schema='autospine.project-component-partitions/v1', authority='none',
                   production_authorized=False, project_id=project_id,
                   source_addresses=deepcopy(inputs.source_addresses),
                   source_plan_sha256=plan_sha, candidate=candidate)
        documents.append(doc)
        entries.append((layer, raw, candidate, canonical_sha256(doc)))
    blank = ownership_template(project_id, entries, inputs.source_addresses, plan_sha,
                               [b['id'] for b in skeleton['bones']])
    proposals = suggest(entries, skeleton, analysis_bindings, blank['sources'])
    ownership = prefill(blank, proposals)
    source = build_mesh(entries, skeleton, ownership, inputs.source_addresses, plan_sha)
    candidate = regions(source, skeleton)
    for row in source['records']:
        if row['status'] == 'blocked':
            blockers.append(dict(layer_id=row['layer_id'], component_id=row['component_id'],
                                 reason_codes=deepcopy(row['reason_codes'])))
    auxiliary = dict(plan=plan, partitions=documents, ownership=ownership,
                     suggestions=proposals, analysis_bindings=analysis_bindings, blockers=blockers,
                     origin=dict(authority='none', production_authorized=False,
                                 human_reviewed=False, origin='automatic_suggestion_experiment'))
    if not candidate['records']:
        raise SleeveOnboardingError('sleeve_mesh_review_required', blockers)
    return source, candidate, template(candidate), auxiliary
