// Browser diagnostics belong to the caller's task, never an immutable runtime.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';

export const CAPTURE_PROCESS_PROFILE='browser-explicit-short-task-log-cwd-v2';
let activePlan;
export function captureProcessOptions(browser,output,environment=process.env,taskDirectory=path.dirname(path.resolve(output))){
  if(typeof browser!=='string'||!browser||typeof output!=='string'||!output)throw Error('capture_process_paths');
  const executablePath=path.resolve(browser),destination=path.resolve(output);
  const cwd=path.resolve(taskDirectory),logFile=path.join(cwd,'chrome.log');
  // Chromium's diagnostic logger does not reliably support extended paths.
  if(cwd.length>220||logFile.length>240)throw Error('capture_process_work_directory_too_long');
  const gpuArgs=path.basename(executablePath).toLowerCase()==='chrome-headless-shell.exe'?['--in-process-gpu']:[];
  return {cwd,logFile,options:{executablePath,headless:true,
    env:{...environment,CHROME_LOG_FILE:logFile},
    args:[...gpuArgs,'--log-file='+logFile,'--enable-logging','--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']}};
}
export async function prepareCaptureProcess(browser,output){
  await fs.mkdir(path.resolve(output),{recursive:true});
  const taskDirectory=await fs.mkdtemp(path.join(os.tmpdir(),'asc-'));
  const plan=captureProcessOptions(browser,output,process.env,taskDirectory);
  activePlan={...plan,output:path.resolve(output)};
  // Playwright has no public launch cwd option. Move only this dedicated Node
  // worker; all CLI asset paths are already absolute before this call.
  process.chdir(plan.cwd);
  return plan.options;
}
export function captureProcessReceipt(){
  if(!activePlan)return {};
  return {capture_process_work_directory:activePlan.cwd,capture_process_log_file:activePlan.logFile};
}
export async function preserveCaptureProcessDiagnostics(){
  if(!activePlan)return;
  // Keep the short original logs and publish durable copies alongside the task.
  // A fallback debug.log remains evidence; it is never silently removed.
  for(const [source,suffix] of [['chrome.log','-browser-debug.log'],['debug.log','-browser-fallback-debug.log']]){
    const file=path.join(activePlan.cwd,source);
    let stat;
    try{stat=await fs.lstat(file);}catch(error){if(error.code==='ENOENT')continue;throw error;}
    if(!stat.isFile()||stat.isSymbolicLink())throw Error('capture_process_log_unsafe');
    const target=path.join(path.dirname(activePlan.output),path.basename(activePlan.output)+suffix);
    await fs.copyFile(file,target);
  }
}
export async function finishCaptureProcess(browser,closeServer=async()=>{},preserve=preserveCaptureProcessDiagnostics){
  try{if(browser)await browser.close();}
  finally{try{await preserve();}finally{await closeServer();}}
}
