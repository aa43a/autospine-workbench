import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {listenForBrowser} from '../../tools/browser-loopback.mjs';

test('browser loopback retries occupied high ports and removes one-shot listeners',async()=>{
  const server=new EventEmitter();let attempts=0;
  server.listen=(port,host)=>{assert.ok(port>=20000&&port<60000);assert.equal(host,'127.0.0.1');attempts++;
    queueMicrotask(()=>attempts===1?server.emit('error',Object.assign(new Error('occupied'),{code:'EADDRINUSE'})):server.emit('listening'));};
  await listenForBrowser(server);assert.equal(attempts,2);
  assert.equal(server.listenerCount('error'),0);assert.equal(server.listenerCount('listening'),0);
});
test('browser loopback does not mask permission failures',async()=>{
  const server=new EventEmitter();server.listen=()=>queueMicrotask(()=>server.emit('error',Object.assign(new Error('denied'),{code:'EACCES'})));
  await assert.rejects(listenForBrowser(server),/denied/);
});
