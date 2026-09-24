"""Read-only comparison of duplicate identity reads and bound snapshots."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.character_jobs import CharacterJobs
from autospine_workbench.automation.sleeve_web_jobs import SleeveWebJobs


def run(project,job):
    projects=ProjectStore(Path('..').resolve(),Path('workspace').resolve())
    sleeves=SleeveWebJobs(projects);characters=CharacterJobs(projects,sleeves);rows=[];expected=None
    try:
        for mode in ('duplicate','snapshot','snapshot','duplicate'):
            with patch.object(characters,'_current',wraps=characters._current) as guard:
                start=perf_counter()
                if mode=='duplicate':
                    files=characters.verified_files(project,job);result=characters.get(project,job)
                else:result,files=characters.verified_snapshot(project,job)
                elapsed=perf_counter()-start
                calls=guard.call_count
            fingerprint={name:sha256(raw).hexdigest() for name,raw in files.items()}
            identity=(result,fingerprint)
            if expected is not None and identity!=expected:raise ValueError('snapshot_result_changed')
            expected=identity
            rows.append(dict(mode=mode,seconds=elapsed,fresh_source_checks=calls,status=result['status'],artifact_sha256=result.get('artifact_sha256'),files=len(files)))
            print(json.dumps(rows[-1]),flush=True)
        return dict(project_id=project,job_id=job,samples=rows,all_file_bytes_equal=True,
                    scope='character_validation_only_not_http_or_full_submission_latency')
    finally:characters.close();sleeves.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project');parser.add_argument('job');parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('output_exists')
    result=run(args.project,args.job)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
