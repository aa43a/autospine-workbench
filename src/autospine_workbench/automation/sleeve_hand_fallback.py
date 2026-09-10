"""Bounded hand-constraint branch using the same exact draft and anchor source."""
import os
from pathlib import Path
import re
import subprocess
import sys
from ..benchmark.mesh_storage import read_mesh_report, publish_mesh_report, export_mesh
from ..asset.planning.sleeve_repair_policy import eligible, select
from ..resolved_project import canonical_sha256
from .storage_io import publish_document


def run(source, project, state, workspace, output):
    from ..project_store import ProjectStore
    from .animated_inputs import load_inputs
    from ..asset.planning.sleeve_hand_rigidity import build as reweight
    from ..asset.planning.sleeve_motion_envelope import build as envelope
    from ..asset.planning.sleeve_helper_review import render
    read = lambda sha: read_mesh_report(state, 'project-component-partitions', sha)
    current = source; anchor = None
    for _ in range(16):
        if current['schema'] == 'autospine.cloth-anchor-correction/v1':anchor = current
        if current['schema'] == 'autospine.sleeve-weights/v1':break
        current = read(current['source_sha256'])
    if anchor is None or current['schema'] != 'autospine.sleeve-weights/v1':
        raise ValueError('sleeve_policy_ancestry')
    garment = current; draft = read(garment['draft_sha256'])
    labels = {(r['layer_id'], r['component_id']): r['assignments'] for r in draft['records']}
    keys = {(r['layer_id'], r['component_id']) for r in source['records']
            if eligible(r, labels[(r['layer_id'], r['component_id'])])}
    if not keys:return source
    with load_inputs(ProjectStore(workspace, state), project) as inputs:
        if source['skeleton_sha256'] != canonical_sha256(inputs.skeleton):
            raise ValueError('sleeve_policy_skeleton')
        amended, domains = reweight(anchor, garment, draft, inputs.skeleton)
        for domain in domains.values():domain['budget_policy'] = 'area-edge-displacement-bound-cap50-v1'
        trial = envelope(amended, inputs.skeleton, domains)
        trial.update(source_sha256=canonical_sha256(anchor), profile='garment-rigid-hand-boundary-sine129-v1')
        inputs.assert_current()
    sha = publish_mesh_report(state, 'project-component-partitions', trial)
    root = output/'hand-branch'; folder = root/'input'/project; folder.mkdir(parents=True, exist_ok=True)
    export_mesh(folder/(sha+'.json'), trial)
    (folder/'index.html').write_text(render(trial).replace('<main>', f'<a href="{sha}.json">完整工件</a><main>'), encoding='utf-8')
    repo = Path(__file__).resolve().parents[3]
    subprocess.run([sys.executable, str(repo/'tools/repair-sleeve-candidate.py'),
        '--input', str(root/'input'), '--output', str(root/'repaired'), '--state-root', str(state),
        '--workspace', str(workspace), '--retained-only', project], check=True,
        env=dict(os.environ), timeout=1500)
    page = (root/'repaired'/project/'index.html').read_text(encoding='utf-8')
    sha = re.search(r'href="([a-f0-9]{64})\.json"', page).group(1)
    repaired = read(sha)
    # Exact readers and this local invocation establish a common reviewed ancestry.
    ancestor = repaired
    for _ in range(8):
        if canonical_sha256(ancestor) == canonical_sha256(trial):break
        ancestor = read(ancestor['source_sha256'])
    else:raise ValueError('sleeve_policy_trial_ancestry')
    result, decisions = select(source, repaired, keys)
    publish_document(root/'selection.json', dict(profile='conditional-hand-repair-v1',
        baseline_sha256=canonical_sha256(source), trial_sha256=sha, records=decisions,
        authority='none', production_authorized=False), staging=root/'.staging')
    publish_mesh_report(state, 'project-component-partitions', result)
    return result
