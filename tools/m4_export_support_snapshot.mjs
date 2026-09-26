// API-only evidence export; does not create a browser, render, or capture frames.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {collectSupportSnapshot} from '../web/modules/motion-support-snapshot.js';
import {supportReportHTML,supportTotals} from '../web/modules/motion-support-report.js';
const [packPath,output,base='http://127.0.0.1:8918']=process.argv.slice(2);
if(!packPath||!output)throw Error('Usage: node tools/m4_export_support_snapshot.mjs PACK_JSON NEW_OUTPUT_DIR [BASE_URL]');
const origin=new URL(base);if(!['http:','https:'].includes(origin.protocol)||origin.username||origin.password)throw Error('invalid_base');
const pack=JSON.parse(await readFile(packPath,'utf8'));
const folder=resolve(output);
await mkdir(folder); // Detect path/permission errors before expensive API verification.
let completed=-1;
const snapshot=await collectSupportSnapshot(pack,async path=>{
  const response=await fetch(origin.origin+path,{signal:AbortSignal.timeout(180000)});
  const value=await response.json();if(!response.ok)throw Error(value.reason_code||`HTTP ${response.status}`);return value;
},{onProgress:p=>{if(p.finished!==completed){completed=p.finished;console.log(`Checked ${p.finished}/${p.total}: ${p.label}`);}}});
const html=supportReportHTML(snapshot,origin.origin);
await writeFile(join(folder,'report.json'),JSON.stringify(snapshot,null,2)+'\n',{flag:'wx'});
await writeFile(join(folder,'index.html'),html,{flag:'wx'});
console.log(JSON.stringify({output:folder,...supportTotals(snapshot)}));
