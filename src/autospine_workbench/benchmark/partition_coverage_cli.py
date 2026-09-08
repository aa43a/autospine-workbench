"""Keep v1 failure identity; publish independently replayable full-alpha v2."""
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..asset.joints.partition_mesh_coverage import improve
from .artifacts import read_input,read_report
from .mesh_storage import read_mesh_report
from .partition_mesh_cli import compile_report
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('improve-partition-coverage',help='Fix alpha coverage and compare distal transition without adopting it')
    for name in ('manifest','workspace','mesh','html'):
        cmd.add_argument('--'+name,type=Path,required=True)
    cmd.add_argument('--output',type=Path)
    cmd.add_argument('--eligibility',choices=('all-alpha','perceptible'),default='perceptible')


def build(state,manifest,digest,workspace,*,supported=False):
    baseline=read_mesh_report(state,manifest['dataset_id'],digest)
    if baseline.get('profile')!='partition-joint-plane-grid-v1':raise ValueError('partition_coverage_profile_invalid')
    expected,(candidate,composite,images)=compile_report(state,manifest,baseline['source_partitions_sha256'],workspace)
    if canonical_sha256(expected)!=digest:raise ValueError('partition_coverage_baseline_mismatch')
    skeleton=read_report(state,manifest['dataset_id'],'assisted-skeleton-candidates',baseline['source_skeleton_sha256'])
    return improve(baseline,candidate,skeleton,images,supported=supported),(candidate,composite,images)


def read_coverage(state,manifest,digest,*,workspace):
    doc=read_mesh_report(state,manifest['dataset_id'],digest)
    expected,_=build(state,manifest,doc['source_mesh_sha256'],workspace,supported=doc.get('profile')=='partition-full-alpha-supported-v2')
    if canonical_sha256(doc)!=canonical_sha256(expected):raise ValueError('partition_coverage_mismatch')
    return doc


def execute(args):
    from .partition_mesh_view import render_mesh
    manifest=read_input(args.manifest)
    report,(candidate,composite,images)=build(args.state_root,manifest,canonical_sha256(read_input(args.mesh)),args.workspace,
                                           supported=args.eligibility=='perceptible')
    html=render_mesh(candidate,report,composite,images)
    html=html.replace('<main>','<p class="notice">本版网格覆盖alpha≥1像素。正式候选沿用原权重规则；踝/腕前移过渡只作为独立试验，不自动采用。</p><main>')
    for trial in report['distal_trials']:
        qa=trial['qa'];minimum=min(p['min_area_ratio'] for p in qa['probes']);inversions=sum(p['inversions'] for p in qa['probes'])
        html=html.replace('</main>',f'<p>{trial["layer_id"]} 前移过渡试验：最小面积比 {minimum:.3f}；翻转样本 {inversions}；未采用。</p></main>')
    export_html(args.html,html)
    return report,'weighted-mesh-candidates',manifest['dataset_id'],0
