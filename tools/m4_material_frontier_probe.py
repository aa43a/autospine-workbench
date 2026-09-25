"""Inspect texture-supported shoulder crossings on three exact frozen candidates."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.material_contact_frontier import locate
from m4_pose_material_review import transfer, alpha_at
from m4_material_anchor_probe import key_times


def run(sources, fields, output):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, name in enumerate(('alice', 'huiye', 'hongmeiling')):
        source = sources / str(index)
        digest = json.loads((source / 'report.json').read_bytes())['candidate_bundle_sha256']
        field = json.loads((fields / (name + '.json')).read_bytes())
        if field['candidate'] != digest:
            raise ValueError('frontier_source_identity_mismatch')
        files = AnimatedStore(source / 'isolated-store').read(digest)
        doc = json.loads(files['skeleton.json'])
        arm, body = field['arm'], field['body']
        if [s['name'] for s in doc['slots']].index(arm) >= [s['name'] for s in doc['slots']].index(body):
            raise ValueError('frontier_body_not_in_front')
        meshes = doc['skins'][0]['attachments']
        am, bm = meshes[arm][arm], meshes[body][body]
        image_names = ['images/' + m.get('path', slot) + '.png' for m, slot in ((am, arm), (bm, body))]
        image, body_image = [np.asarray(Image.open(BytesIO(files[n])).convert('RGBA')) for n in image_names]
        h, w = image.shape[:2]
        y, x = np.mgrid[:h, :w]
        uv = np.column_stack(((x.ravel()+.5)/w, (y.ravel()+.5)/h))
        setup, bones = sample(dict(doc, animations={'setup': {}}), 'setup', 0)
        world, covered = transfer(np.asarray(am['uvs']).reshape(-1, 2), setup[arm], am['triangles'], uv)
        buv = np.full_like(world, np.nan)
        buv[covered], _ = transfer(setup[body], np.asarray(bm['uvs']).reshape(-1, 2), bm['triangles'], world[covered])
        root = np.asarray(bones['upperarm_r'][:2])
        radius = .65 * np.linalg.norm(np.asarray(bones['forearm_r'][:2])-root)
        result = locate(image[:, :, 3], alpha_at(body_image[:, :, 3], buv).reshape(h, w),
                        world.reshape(h, w, 2), covered.reshape(h, w), root, radius)
        result.update(character=name, artifact_sha256=digest, arm=arm, body=body,
                      textures={n: sha256(files[n]).hexdigest() for n in image_names}, frames=[])
        points = np.asarray([s['world'] for s in result['samples']]).reshape(-1, 2)
        marked = Image.fromarray(image)
        draw = ImageDraw.Draw(marked)
        for item in result['samples']:
            u, v = item['uv']; draw.ellipse((u*w-1, v*h-1, u*w+1, v*h+1), fill=(255, 90, 40, 255))
        marked.save(output / (name + '-frontier.png'))
        if len(points):
            body_uv, body_valid = transfer(setup[body], np.asarray(bm['uvs']).reshape(-1, 2), bm['triangles'], points)
            body_marked = Image.fromarray(body_image)
            body_draw = ImageDraw.Draw(body_marked)
            bh, bw = body_image.shape[:2]
            for u, v in body_uv[body_valid]:
                body_draw.ellipse((u*bw-1, v*bh-1, u*bw+1, v*bh+1), fill=(255, 90, 40, 255))
            body_marked.save(output / (name + '-body-frontier.png'))
            # Motion time zero may differ from setup; verify the actual static reference independently.
            sa, sav = transfer(setup[arm], setup[arm], am['triangles'], points)
            sb, sbv = transfer(setup[body], setup[body], bm['triangles'], points)
            if not (sav & sbv).all() or np.max(np.abs(sa-sb)) > 1e-6:
                raise ValueError('frontier_setup_correspondence_invalid')
            result['setup_maximum_pair_error_px'] = float(np.linalg.norm(sa-sb, axis=1).max())
            duration = max(key_times(doc['animations']['external-motion']))
            for time in (0., duration*.43125, duration):
                posed = sample(doc, 'external-motion', time)[0]
                a, av = transfer(setup[arm], posed[arm], am['triangles'], points)
                b, bv = transfer(setup[body], posed[body], bm['triangles'], points)
                valid = av & bv
                gap = np.linalg.norm(a[valid]-b[valid], axis=1)
                result['frames'].append(dict(time=time, supported=int(valid.sum()), missing=int((~valid).sum()),
                    maximum_gap_px=float(gap.max()) if len(gap) else None,
                    median_gap_px=float(np.median(gap)) if len(gap) else None))
        rows.append(result)
    (output / 'report.json').write_text(json.dumps(dict(selected=False, authority='none', records=rows), indent=2), encoding='utf8')
    print(json.dumps([dict(character=r['character'], crossings=len(r['samples']), frames=r['frames']) for r in rows]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('sources', 'fields', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    run(args.sources, args.fields, args.output)
