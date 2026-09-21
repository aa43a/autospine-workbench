"""Plot verified source previews for category inspection, without review authority."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from m4_motion_cohort import api, digest


def render(preview, title):
    frames = preview['frames']
    indices = sorted({round(i*(len(frames)-1)/5) for i in range(6)})
    image = Image.new('RGB', (1560, 760), '#101923'); draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    draw.text((20, 12), title + ' | source samples, not target acceptance', fill='white', font=font)
    for view in range(2):
        project = (lambda p: (p[0], -p[1])) if view == 0 else (lambda p: (-p[2], -p[1]))
        points = [project(p) for f in frames for p in f['joints']]
        low = [min(p[a] for p in points) for a in (0, 1)]
        high = [max(p[a] for p in points) for a in (0, 1)]
        scale = min(220/max(high[0]-low[0], 1e-8), 285/max(high[1]-low[1], 1e-8))
        y = 45 + view*350
        draw.text((10, y), 'Front (+X,-Y)' if view == 0 else 'Side (-Z,-Y)', fill='#91d7ef', font=font)
        for col, index in enumerate(indices):
            frame = frames[index]
            def point(p):
                x, yy = project(p)
                return (col*260+130+(x-(low[0]+high[0])/2)*scale,
                        y+185+(yy-(low[1]+high[1])/2)*scale)
            draw.text((col*260+15, y+27), f"{frame['time']:.3f}s / frame {frame['frame']}", fill='white', font=font)
            for joint, parent in enumerate(preview['parents']):
                if parent is None: continue
                name = preview['names'][joint].lower()
                color = '#ffb579' if 'left' in name else '#6bc9ff' if 'right' in name else '#e1edf0'
                draw.line([point(frame['joints'][parent]), point(frame['joints'][joint])], fill=color, width=3)
    return image, indices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'state', 'output'): parser.add_argument(name, type=Path)
    args = parser.parse_args()
    plan, state = [json.loads(p.read_text(encoding='utf-8')) for p in (args.plan, args.state)]
    if state['plan_sha256'] != digest(plan): raise ValueError('source_sheet_plan_mismatch')
    args.output.mkdir(exist_ok=False)
    records = []; cards = []
    for motion in plan['motions']:
        job = state['sources'][motion['id']]['job_id']
        base = '/api/motions/' + job
        source = api('http://127.0.0.1:8918', base)
        if source['status'] != 'succeeded' or source['source_sha256'] != motion['sha256']:
            raise ValueError('source_sheet_source_mismatch')
        preview = api('http://127.0.0.1:8918', base + '/preview')
        if digest(preview) != source['result']['preview_sha256']:
            raise ValueError('source_sheet_preview_mismatch')
        image, indices = render(preview, motion['id'])
        name = job + '.png'; image.save(args.output / name)
        records.append(dict(motion_id=motion['id'], source_job_id=job, source_sha256=motion['sha256'],
            preview_sha256=digest(preview), preview_samples=len(preview['frames']),
            selected_frames=[preview['frames'][i]['frame'] for i in indices],
            image=name, image_sha256=sha256((args.output/name).read_bytes()).hexdigest()))
        cards.append('<h2>'+escape(motion['id'])+'</h2><img style="width:100%" src="'+name+'">')
        print(motion['id'], name, flush=True)
    receipt = dict(profile='verified-source-motion-contact-sheets-v1', plan_sha256=digest(plan),
        records=records, authority='none', scope='six_sample_poses_per_source_not_continuous_motion_or_human_acceptance')
    (args.output/'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Source motion samples</title>'
        '<body style="background:#101923;color:white;font:18px system-ui">'
        '<h1>Source category inspection</h1><p>Orange: left; blue: right. '
        'Six sampled poses in two projections. Not character animation acceptance.</p>'+''.join(cards), encoding='utf-8')


if __name__ == '__main__': main()
