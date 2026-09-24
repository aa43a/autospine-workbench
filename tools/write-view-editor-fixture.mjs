// Generate a visibly synthetic UI fixture; no character data or acceptance writes.
import fs from 'node:fs/promises';
const output=process.argv[2];if(!output)throw Error('Output HTML path required');
await fs.writeFile(output,`<!doctype html><meta charset="utf-8"><title>新视角画布交互验证</title>
<style>body{background:#101923;color:#eee;font:16px sans-serif;margin:20px}fieldset{max-width:1100px}button,input,select{font:inherit;margin:6px}canvas{display:block}label{display:inline-block}</style>
<h1>新视角画布交互验证 · 合成网格</h1><p>双色矩形仅验证编辑功能，不是角色材质或视觉验收。</p><button id="restore">重新载入回交草稿</button><main></main><pre id="output"></pre>
<script type="module">
import {viewEditor} from '/modules/view-pose-editor.js';
import {restoreViewDraft} from '/modules/view-pose-restore.js';
const template={request:{draft_revision:1},view_pose:{interval:[0,4],poses:[]},control_template:{mesh_sha256:'synthetic',source_uv:[[0,0],[1,0],[1,1],[0,1]],target_uv:[[0,0],[1,0],[1,1],[0,1]],target_xy:[[0,200],[100,200],[100,0],[0,0]],triangles:[[0,1,2],[0,2,3]]}};
const image=document.createElement('canvas');image.width=100;image.height=200;const ctx=image.getContext('2d');ctx.fillStyle='#e08030';ctx.fillRect(0,0,100,200);ctx.fillStyle='#3090e0';ctx.fillRect(0,100,100,100);
let saved=null;
const editor=viewEditor(document.querySelector('main'),value=>{saved=JSON.stringify(value);document.querySelector('#output').textContent=JSON.stringify(value.view_pose,null,2);},()=>document.querySelector('#output').textContent='回交结果已失效');
editor.load(template,await createImageBitmap(image));
document.querySelector('#restore').onclick=async()=>{if(!saved)return;editor.load(restoreViewDraft(template,JSON.parse(saved)),await createImageBitmap(image),4);};
</script>`);
console.log(output);
