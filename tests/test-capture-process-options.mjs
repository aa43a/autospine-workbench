import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {spawnSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {captureProcessOptions,CAPTURE_PROCESS_PROFILE,finishCaptureProcess} from '../tools/capture-process-options.mjs';

test('Diagnostic copy failure still closes the listener and remains an error',async()=>{
  const calls=[];
  await assert.rejects(finishCaptureProcess({close:async()=>calls.push('browser')},
    async()=>calls.push('listener'),async()=>{calls.push('diagnostics');throw Error('copy failed');}),/copy failed/);
  assert.deepEqual(calls,['browser','diagnostics','listener']);
});

test('Browser close failure still preserves diagnostics and closes the listener',async()=>{
  const calls=[];
  await assert.rejects(finishCaptureProcess({close:async()=>{calls.push('browser');throw Error('browser close failed');}},
    async()=>calls.push('listener'),async()=>calls.push('diagnostics')),/browser close failed/);
  assert.deepEqual(calls,['browser','diagnostics','listener']);
});

test('Headless Shell receives matching explicit/env short log and its isolated GPU mode',()=>{
  const task=path.join(os.tmpdir(),'owned-capture');
  const plan=captureProcessOptions('tools/chrome-headless-shell.exe','very/long/output',{EXISTING:'kept'},task);
  assert.equal(plan.options.executablePath,path.resolve('tools/chrome-headless-shell.exe'));
  assert.equal(plan.options.env.EXISTING,'kept');
  assert.equal(plan.options.env.CHROME_LOG_FILE,plan.logFile);
  assert.ok(plan.options.args.includes('--log-file='+plan.logFile));
  assert.ok(plan.options.args.includes('--in-process-gpu'));
  assert.equal(plan.cwd,path.resolve(task));
  assert.ok(plan.logFile.length<=240);
  assert.equal(CAPTURE_PROCESS_PROFILE,'browser-explicit-short-task-log-cwd-v2');
});

test('External Chrome and Edge retain the historical GPU process behavior',()=>{
  for(const name of ['chrome.exe','msedge.exe']){
    const plan=captureProcessOptions(name,'output',{},os.tmpdir());
    assert.ok(!plan.options.args.includes('--in-process-gpu'));
    assert.ok(plan.options.args.includes('--use-angle=swiftshader'));
    assert.ok(plan.options.args.includes('--enable-webgl'));
    assert.ok(plan.options.args.includes('--log-file='+plan.options.env.CHROME_LOG_FILE));
  }
});

test('Unusable diagnostic paths fail rather than launching from the software directory',()=>{
  assert.throws(()=>captureProcessOptions('browser','output',{},path.join(os.tmpdir(),'x'.repeat(241))),/too_long/);
});

test('Long task output gets a unique short cwd; original and durable diagnostics survive',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'capture-options-test-'));
  const helper=pathToFileURL(path.resolve('tools/capture-process-options.mjs')).href;
  const relative=path.join(...Array.from({length:8},(_,i)=>'capture-output-segment-'+i));
  const output=path.join(root,relative);
  const worker='import fs from "node:fs/promises";import path from "node:path";'+
    'import {prepareCaptureProcess,captureProcessReceipt,preserveCaptureProcessDiagnostics} from '+JSON.stringify(helper)+';'+
    'const output=path.resolve(process.argv[1]);const options=await prepareCaptureProcess("relative-browser.exe",process.argv[1]);'+
    'const receipt=captureProcessReceipt();await fs.writeFile(receipt.capture_process_log_file,"explicit log");'+
    'await fs.writeFile(path.join(process.cwd(),"debug.log"),"fallback evidence");'+
    'await preserveCaptureProcessDiagnostics();process.stdout.write(JSON.stringify({options,receipt,cwd:process.cwd(),output}));';
  const receipts=[];
  try{
    for(let i=0;i<2;i++){
      const run=spawnSync(process.execPath,['--input-type=module','-e',worker,relative],{cwd:root,encoding:'utf8'});
      assert.equal(run.status,0,run.stderr);
      const result=JSON.parse(run.stdout);receipts.push(result.receipt);
      assert.equal(result.output,output);
      assert.equal(result.options.executablePath,path.join(root,'relative-browser.exe'));
      assert.ok(result.receipt.capture_process_log_file.length<=240);
      assert.equal(result.cwd,result.receipt.capture_process_work_directory);
      assert.notEqual(result.cwd,root);
      assert.equal(await fs.readFile(result.receipt.capture_process_log_file,'utf8'),'explicit log');
      assert.equal(await fs.readFile(path.join(result.cwd,'debug.log'),'utf8'),'fallback evidence');
      assert.equal(await fs.readFile(path.join(path.dirname(output),path.basename(output)+'-browser-debug.log'),'utf8'),'explicit log');
      assert.equal(await fs.readFile(path.join(path.dirname(output),path.basename(output)+'-browser-fallback-debug.log'),'utf8'),'fallback evidence');
      assert.equal((await fs.readdir(root)).includes('debug.log'),false);
    }
    assert.notEqual(receipts[0].capture_process_work_directory,receipts[1].capture_process_work_directory);
  }finally{
    for(const receipt of receipts){
      const owned=path.resolve(receipt.capture_process_work_directory);
      assert.equal(path.dirname(owned),path.resolve(os.tmpdir()));
      assert.ok(path.basename(owned).startsWith('asc-'));
      await fs.rm(owned,{recursive:true,force:true});
    }
    assert.equal(path.dirname(path.resolve(root)),path.resolve(os.tmpdir()));
    await fs.rm(root,{recursive:true,force:true});
  }
});
