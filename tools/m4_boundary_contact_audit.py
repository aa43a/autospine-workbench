"""Compare final candidate ankle proxies to the immutable parent on every Runtime time."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.final_contact_batches import inspect
from autospine_workbench.targets.character43.runtime_storage_reference import stored_document
from m4_transverse_batch_audit import audit


def run(state,probe,runtime,output):
    coverage=audit(state,probe,runtime)
    receipt=json.loads((runtime/'report.json').read_bytes())
    parent=AnimatedStore(state).read(receipt['parent_artifact_sha256'])
    first=receipt['rows'][0];files=AnimatedStore(runtime/first['folder']/'isolated-store').read(first['candidate_bundle_sha256'])
    motion=json.loads(parent['motion-ir.json']);contact=json.loads(parent['motion-contact.json'])
    length=json.loads(parent['motion-review.json'])['reference_length_px'];times=receipt['required_times']
    documents={'parent':json.loads(parent['skeleton.json']),'candidate':json.loads(files['skeleton.json'])}
    documents['runtime_storage']=stored_document(documents['candidate'])
    output.mkdir(parents=True,exist_ok=False);results={}
    for name,document in documents.items():
        print(json.dumps(dict(stage='ankle_proxy',representation=name,times=len(times))),flush=True)
        results[name]=inspect(document,'external-motion',motion,contact,times,length)
    report=dict(profile='boundary-final-contact-comparison-v1',parent_artifact_sha256=receipt['parent_artifact_sha256'],
        skeleton_sha256=receipt['skeleton_sha256'],runtime_coverage=coverage,
        runtime_report_sha256=sha256((runtime/'report.json').read_bytes()).hexdigest(),
        inputs={name:sha256(parent[name]).hexdigest() for name in ('motion-ir.json','motion-contact.json','motion-review.json')},
        results=results,parent_candidate_equal=results['parent']['after']==results['candidate']['after'],
        pending_checks=['mesh_contact','depth','visual'],authority='none',selected=False,production_authorized=False)
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps({k:dict(status=v['after']['status'],max_drift_px=v['after']['max_drift_px']) for k,v in results.items()}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('state','probe','runtime','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.state,args.probe,args.runtime,args.output)
