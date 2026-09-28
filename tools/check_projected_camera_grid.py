"""Compare next grid against current camera-only sampling using real observations."""
import json,sys,math
from pathlib import Path
from autospine_workbench.targets.character43.projected_camera_sampling import refine,PROFILE
from autospine_workbench.targets.character43.camera_sampling import interpolate
from autospine_workbench.targets.character43.camera_track import sample
from autospine_workbench.targets.character43.oblique_motion import project
folder=Path(sys.argv[1]);source=json.loads((folder/'editor-source.json').read_text())
rows=[]
for name in ('fixed','turn','roundtrip'):
    camera=json.loads((folder/f'{name}-camera.json').read_text())
    times=refine(source['times'],source['vectors'],camera['keys'],source['duration'],source['reference'])
    maximum=0
    for values in source['vectors'].values():
        angles=[]
        for t,v in zip(times,interpolate(values,source['times'],times)):
            x,y,_=project(v,sample(camera['keys'],t));angles.append(math.degrees(math.atan2(y,x)))
        maximum=max(maximum,max(abs((b-a+180)%360-180) for a,b in zip(angles,angles[1:])))
    assert maximum<=12+1e-8
    rows.append(dict(name=name,times=times,previous_count=len(camera['times']),maximum_direction_step=maximum))
(folder/'projected-grid.json').write_text(json.dumps(dict(profile=PROFILE,rows=rows),indent=2))
print(json.dumps([dict(name=r['name'],count=len(r['times']),maximum=r['maximum_direction_step']) for r in rows]))
