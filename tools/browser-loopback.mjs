import {randomInt} from 'node:crypto';

// Windows may allocate a browser-restricted low port for listen(0).
// Bind a high loopback port instead; no browser security flags are disabled.
export async function listenForBrowser(server){
  for(let attempt=0;attempt<32;attempt++){
    const port=randomInt(20000,60000);
    try{
      await new Promise((resolve,reject)=>{
        const fail=error=>{server.off('listening',ready);reject(error);};
        const ready=()=>{server.off('error',fail);resolve();};
        server.once('error',fail);server.once('listening',ready);server.listen(port,'127.0.0.1');
      });
      return;
    }catch(error){if(error.code!=='EADDRINUSE')throw error;}
  }
  throw new Error('browser_loopback_port_unavailable');
}
