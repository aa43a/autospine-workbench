"""Compare new weight identities with exact previous final candidates, exposing regressions."""
import argparse
from html import escape
from pathlib import Path
import re
from autospine_workbench.benchmark.mesh_storage import read_mesh_report
from autospine_workbench.benchmark.artifacts import publish_report,export_document
from autospine_workbench.asset.planning.component_collar_keys import score
from autospine_workbench.asset.planning.component_temporal_qa import passed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',action='append',required=True,help='project=old-directory=new-directory')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=parser.parse_args();cases=[];html=[]
    def read(folder):
        page=(folder/'keys.html').read_text(encoding='utf-8')
        digest=re.search(r'href="([a-f0-9]{64})\.json"',page).group(1)
        return digest,read_mesh_report(args.state_root,'project-component-partitions',digest)
    for item in args.case:
        project,a,b=item.split('=',2);oldpath,newpath=Path(a),Path(b)
        oldsha,old=read(oldpath);newsha,new=read(newpath)
        trialsource=read_mesh_report(args.state_root,'project-component-partitions',new['source_sha256'])
        if (trialsource['source_sha256']!=old['source_sha256'] or old['project_id']!=project or new['project_id']!=project
                or old['skeleton_sha256']!=new['skeleton_sha256']):raise ValueError('distal_comparison_source_mismatch')
        lookup={(c['layer_id'],c['component_id'],c['bone_id']):c for c in old['comparisons']}
        if set(lookup)!={(c['layer_id'],c['component_id'],c['bone_id']) for c in new['comparisons']}:raise ValueError('distal_comparison_inventory_mismatch')
        regions={}
        for c in new['comparisons']:
            baseline=lookup[c['layer_id'],c['component_id'],c['bone_id']]
            r=regions.setdefault((c['layer_id'],c['component_id']),dict(before=[0,0,0],trial=[0,0,0],new_failure_times=[],new_inversion_times=[]))
            for i,(before,after) in enumerate(zip(baseline['after'],c['after'])):
                if passed(before) and not passed(after):r['new_failure_times'].append([c['bone_id'],i/4])
                if after['inversions']>before['inversions']:r['new_inversion_times'].append([c['bone_id'],i/4])
            r['before']=[x+y for x,y in zip(r['before'],score(baseline['after']))]
            r['trial']=[x+y for x,y in zip(r['trial'],score(c['after']))]
        records=[]
        for (layer,component),r in regions.items():
            improved=(not r['new_failure_times'] and not r['new_inversion_times'] and all(a<=b for a,b in zip(r['trial'],r['before'])) and r['trial']!=r['before'])
            records.append(dict(layer_id=layer,component_id=component,nonregressing_improvement=improved,**r))
        before=[sum(r['before'][i] for r in records) for i in (0,1)]
        after=[sum(r['trial'][i] for r in records) for i in (0,1)]
        regression=sum(len(r['new_inversion_times']) for r in records)
        cases.append(dict(project_id=project,old_keys_sha256=oldsha,trial_keys_sha256=newsha,regions=records))
        html.append(f'<tr><td>{escape(project)}</td><td>{before[0]} → {after[0]}</td><td>{before[1]} → {after[1]}</td><td>{regression}</td>'
                    f'<td><a href="{escape((oldpath.resolve()/"keys.html").as_uri(),quote=True)}">原结果</a> / <a href="{escape((newpath.resolve()/"keys.html").as_uri(),quote=True)}">完整试验（含回归）</a></td></tr>')
    document=dict(schema='autospine.parent-distal-comparison/v1',authority='none',production_authorized=False,cases=cases,global_replacement_authorized=False)
    digest=publish_report(args.state_root,'project-component-partitions','parent-distal-comparison-v1',document)
    args.output.mkdir(parents=True,exist_ok=True);export_document(args.output/f'{digest}.json',document)
    page='<html lang="zh-CN"><meta charset="utf-8"><title>末端权重跨角色对照</title><style>body{background:#17212d;color:white;font:17px system-ui;margin:30px}a{color:#9df}td,th{padding:14px;border:1px solid #789}table{border-collapse:collapse}</style><h1>同一末端权重规则：收益与回归</h1>'
    page+='<p>此表比较上一版最终结果与新权重重新生成的全部修正。试验含回归，没有全局替换旧方案；逐区域回归时间点保存在数据中。</p>'
    page+='<table><tr><th>角色</th><th>失败采样</th><th>翻转总数</th><th>翻转增加的采样点</th><th>播放对照</th></tr>'+''.join(html)+'</table>'
    page+=f'<p>零翻转不等于全部通过。所有结果仍是候选，没有Runtime或完整角色验收。</p><a href="{digest}.json">逐区域回归证据</a></html>'
    (args.output/'index.html').write_text(page,encoding='utf-8')
    print(digest)


if __name__=='__main__':main()
