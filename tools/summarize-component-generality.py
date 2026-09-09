"""Compare fixed algorithms on supplied visible cohort report directories."""
import argparse
import hashlib
from html import escape
from pathlib import Path
import re
from autospine_workbench.benchmark.mesh_storage import read_mesh_report
from autospine_workbench.benchmark.artifacts import publish_report,export_document
from autospine_workbench.asset.planning.component_temporal_qa import passed
from autospine_workbench.asset.planning.component_collar_keys import score


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',action='append',required=True,help='project=report-directory')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=parser.parse_args();cases=[];links=[]
    for item in args.case:
        project,path=item.split('=',1);folder=Path(path)
        documents={};digests={}
        for page,kind in [('fk.html','fk'),('keys.html','keys')]:
            match=re.search(r'href="([a-f0-9]{64})\.json"',(folder/page).read_text(encoding='utf-8'))
            if not match:raise ValueError('cohort_report_missing')
            digests[kind]=match.group(1)
            documents[kind]=read_mesh_report(args.state_root,'project-component-partitions',match.group(1))
            if documents[kind]['project_id']!=project:raise ValueError('cohort_project_mismatch')
        fk,keys=documents['fk'],documents['keys']
        if fk['source_sha256']!=keys['source_sha256'] or fk['skeleton_sha256']!=keys['skeleton_sha256']:
            raise ValueError('cohort_source_mismatch')
        collar=read_mesh_report(args.state_root,'project-component-partitions',keys['collar_sha256'])
        if collar['correction_sha256']!=fk['correction_sha256']:
            raise ValueError('cohort_correction_mismatch')
        before=[sum(not passed(t['after']) for r in fk['rows'] for t in r['ticks']),sum(t['after']['inversions'] for r in fk['rows'] for t in r['ticks'])]
        after=[sum(score(c['after'])[i] for c in keys['comparisons']) for i in (0,1)]
        origin='automatic_suggestion_experiment' if (folder/'draft-origin.json').exists() else 'supplied_draft'
        cases.append(dict(project_id=project,origin=origin,addresses=digests,samples=len(fk['rows'])*33,
                          failures_before=before[0],failures_after=after[0],inversions_before=before[1],inversions_after=after[1]))
        links.append(f'<tr><td><a href="{escape((folder.resolve()/"keys.html").as_uri(),quote=True)}">{escape(project)}</a></td><td>{origin}</td><td>{len(fk["rows"])*33}</td><td>{before[0]} → {after[0]}</td><td>{before[1]} → {after[1]}</td></tr>')
    root=Path('src/autospine_workbench')
    files=sorted((root/'asset/planning').glob('component_*.py'))
    files+=sorted((root/'asset/joints').glob('*weight*.py'))
    files+=sorted((root/'asset/joints').glob('partition_mesh*.py'))
    document=dict(schema='autospine.component-generality-report/v1',authority='none',production_authorized=False,
        cases=cases,scope='visible_cohort_and_procedural_tests_not_holdout',accuracy_claimed=False,
        algorithm_files={str(p).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    digest=publish_report(args.state_root,'project-component-partitions','generality-v1',document)
    args.output.mkdir(parents=True,exist_ok=True);export_document(args.output/f'{digest}.json',document)
    page='<html lang="zh-CN"><meta charset="utf-8"><title>局部修正跨角色验证</title><style>body{background:#17212d;color:#eee;font:17px system-ui;margin:30px}a{color:#9de0ff}td,th{padding:14px;border:1px solid #789}table{border-collapse:collapse}</style><h1>固定方法跨角色验证</h1>'
    page+='<p>同一算法与阈值，未按角色写规则；此处统计数值失败，不表示人工标注正确率。自动建议草稿未被人工批准。未使用 holdout。</p>'
    page+='<table><tr><th>角色/播放</th><th>草稿来源</th><th>采样数</th><th>失败点：局部修正前→后</th><th>翻转总数</th></tr>'+''.join(links)+'</table>'
    page+=f'<p>对照起点是之前的FK局部修正，终点是关节邻域与逐关键姿态回归后的结果。所有角色仍有失败，不能宣称通用自动绑骨达标。</p><a href="{digest}.json">来源内容地址与算法文件摘要</a></html>'
    (args.output/'index.html').write_text(page,encoding='utf-8')
    print(digest)


if __name__=='__main__':main()
