"""Self-contained, exact-candidate context for a material handoff."""
import base64
import json

from .pipeline_run import PipelineRunError


def build(read, row):
    def asset(name):
        return read(['player-assets', name])[0]
    scene = asset('scene.json')
    document = json.loads(scene)
    if document.get('artifact_sha256') != row['artifact_sha256']:
        raise PipelineRunError('motion_material_preview_identity_changed')
    if (row['animation'] not in document['skeleton']['animations']
            or row['slot'] not in {s['name'] for s in document['skeleton']['slots']}):
        raise PipelineRunError('motion_material_preview_event_invalid')
    if len(scene) > 64 << 20:
        raise PipelineRunError('motion_material_preview_too_large')
    html = read(['player.html'])[0].decode('utf-8')
    client = asset('client.js').decode('utf-8')
    marker = 'const get = async name => {'
    if client.count(marker) != 1:
        raise PipelineRunError('motion_material_preview_client_changed')
    payload = base64.b64encode(scene).decode('ascii')
    client = client.replace(marker, marker +
        ' if(name==="scene.json")return new Response(Uint8Array.from(atob("'+payload+'"),c=>c.charCodeAt(0)));')
    def script(raw):
        return raw.replace('</script', '<\\/script')
    event = json.dumps(dict(artifact=row['artifact_sha256'], animation=row['animation'],
                           slot=row['slot'], triangle=row['event']['triangle'], time=row['event']['time']))
    boot = '''
const event=EVENT;let attempts=0;
const locate=setInterval(()=>{
 if(window.characterPlayerError||++attempts>1200){clearInterval(locate);return;}
 const control=window.characterPlayerControl;if(!control)return;clearInterval(locate);
 if(control.artifact!==event.artifact)throw Error('material candidate mismatch');
 const select=document.getElementById('motion');select.value=event.animation;select.dispatchEvent(new Event('change'));
 if(!control.seek(event.time)||!control.inspectTriangle(event.slot,event.triangle,event.animation))
   document.getElementById('status').textContent='异常定位失败，请核对动作与时间';
},100);
'''.replace('EVENT', event)
    html = html.replace('<link rel="stylesheet" href="player-assets/style.css">',
                        '<style>'+asset('style.css').decode().replace('</style', '<\\/style')+'</style>')
    inspection = asset('inspection.js').decode().replace(
        "parent.postMessage({type:'audit-player-ready'},location.origin);",
        "if(location.origin!=='null')parent.postMessage({type:'audit-player-ready'},location.origin);")
    for name, source in [('runtime.js', asset('runtime.js').decode()),
                         ('inspection.js', inspection), ('client.js', client)]:
        tag = ('<script id="runtime" src="player-assets/runtime.js" async></script>' if name == 'runtime.js'
               else f'<script src="player-assets/{name}"></script>')
        if html.count(tag) != 1:
            raise PipelineRunError('motion_material_preview_template_changed')
        html = html.replace(tag, '<script>'+script(source)+'</script>')
    start = html.index('<footer>'); end = html.index('</footer>', start)+len('</footer>')
    html = html[:start]+('<footer>素材任务上下文：显示实际失败候选，不是正确姿态参考。'
        '可拖动检查邻近时刻；原素材、绑定和验收均不改变。<p id="identity"></p></footer>')+html[end:]
    return html.replace('</body>', '').replace('</html>', '<script>'+script(boot)+'</script></html>').encode('utf-8')
