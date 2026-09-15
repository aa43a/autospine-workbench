"""Build a source-preserving isolated dress component candidate; no adoption."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.component_mount_candidate import generate as split
from autospine_workbench.targets.character43.skirt_candidate import generate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--character',required=True)
    parser.add_argument('--slot',required=True)
    parser.add_argument('--component',required=True)
    args=parser.parse_args();store=AnimatedStore(args.state_root)
    files=store.read(args.character);doc=json.loads(files['skeleton.json'])
    attachment=doc['skins'][0]['attachments'][args.slot][args.slot]
    parent=doc['bones'][attachment['vertices'][1]]['name']
    partitioned,report=split(files,args.slot,[parent],partition_only=True)
    if args.component not in {r['component_id'] for r in report['parts'] if r['component_id']!='unbound-residual'}:
        raise ValueError('skirt_dress_component_missing')
    split_digest=store.publish(partitioned)
    output,report=generate(partitioned,split_digest,[args.slot+'-'+args.component],
                           waist_driver='candidate-chest-v1',dress_components=True)
    digest=store.publish(output)
    print(json.dumps(dict(source_sha256=args.character,partition_sha256=split_digest,
        artifact_sha256=digest,geometry_passed=report['geometry_passed'],status=report['status'],
        blocked_layers=report.get('blocked_layers',[]),waists=[r['contact'] for r in report['rows']],authority='none')))


if __name__=='__main__':main()
