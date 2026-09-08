"""Exact partition sources -> residual policy comparison and reversible drafts."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from ..resolved_project import canonical_sha256
from ..asset.joints.residual_policy import apply_policy
from .artifacts import read_input,read_report,publish_report,export_document
from .partition_cli import build
from .residual_draft import build_draft,validate_draft
from .mapping_cli import export_html


def register_parser(sub):
    cmd=sub.add_parser('review-partition-residuals',help='Compare bounded residual assignment and save a review draft')
    for name in ('manifest','workspace','partitions','html','draft-output'):
        cmd.add_argument('--'+name,type=Path,required=True)
    for name in ('draft','output'):cmd.add_argument('--'+name,type=Path)


def sources(state,manifest,digest,workspace):
    saved=read_report(state,manifest['dataset_id'],'layer-partitions',digest)
    partitions,data,view=build(state,manifest,saved['source_structure_sha256'],workspace)
    if canonical_sha256(partitions)!=digest:raise ValueError('residual_partition_mismatch')
    return partitions,data,view


def analyze(partitions,data,draft):
    validate_draft(partitions,draft);rows=[];previews=[]
    with ZipFile(BytesIO(data)) as zipped:
        for row,record in zip(partitions['layers'],draft['records']):
            prefix=row['layer_id']+'/'
            source=zipped.read(prefix+'source.png');mask=zipped.read(prefix+'ownership.png')
            retained,before=apply_policy(source,mask,'retain')
            proposed,qa=apply_policy(source,mask,'nearest_4px')
            selected=qa if record['policy']=='nearest_4px' else before
            rows.append({'layer_id':row['layer_id'],'selected_policy':record['policy'],
                         'proposal_qa':qa,'selected_qa':selected,'status':'needs_review'})
            previews.append((row['layer_id'],retained['residual.png'],proposed['residual.png'],qa))
    report={'schema':'autospine.residual-review/v1','profile':'bounded-nearest-low-alpha-4px-v1',
            'authority':'none','production_authorized':False,'source_partitions_sha256':canonical_sha256(partitions),
            'source_draft_sha256':canonical_sha256(draft),'layers':rows}
    return report,previews


def read_review(state,manifest,digest,*,workspace):
    doc=read_report(state,manifest['dataset_id'],'residual-reviews',digest)
    partitions,data,_=sources(state,manifest,doc['source_partitions_sha256'],workspace)
    draft=read_report(state,manifest['dataset_id'],'residual-drafts',doc['source_draft_sha256'])
    expected,_=analyze(partitions,data,draft)
    if canonical_sha256(doc)!=canonical_sha256(expected):raise ValueError('residual_review_mismatch')
    return doc


def execute(args):
    from .residual_view import render_review
    manifest=read_input(args.manifest)
    partitions,data,(candidate,composite,_)=sources(args.state_root,manifest,canonical_sha256(read_input(args.partitions)),args.workspace)
    draft=validate_draft(partitions,read_input(args.draft)) if args.draft else build_draft(partitions)
    report,previews=analyze(partitions,data,draft)
    publish_report(args.state_root,manifest['dataset_id'],'residual-drafts',draft)
    export_document(args.draft_output,draft)
    export_html(args.html,render_review(candidate,composite,partitions,draft,previews))
    return report,'residual-reviews',manifest['dataset_id'],0
