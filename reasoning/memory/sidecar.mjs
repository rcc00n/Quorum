// Unmodified official reference engine; no HTTP service, provider or vendor copy.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL,fileURLToPath} from 'node:url';
const home=process.env.METERLESS_HOME;
if(!home)throw Error('Reference engine checkout required');
export const {HMEM}=await import(pathToFileURL(path.join(home,'engines/hmem/reference/src/index.ts')).href);
if(process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  process.umask(0o077);
  try {
    const raw=fs.readFileSync(0,'utf8');if(Buffer.byteLength(raw)>2*1024*1024)throw Error('Request too large');
    const request=JSON.parse(raw);
    if(request.dry_run!==false||process.env.QUORUM_DRY_RUN==='1'){console.log(JSON.stringify({rows:[],count:0,ledger_entries:0,disabled:true}));process.exit(0);}
    const dir=process.env.QUORUM_HMEM_DIR;
    if(!dir||!path.isAbsolute(dir))throw Error('Private external directory required');
    // DECISION(2026-10-24, rcc00n/Codex): reject linked stores and validate ownership markers.
    // Why: the reference engine follows file links when persisting state and its trust ledger.
    const inspectStore=()=>{
      for(let parent=dir;;parent=path.dirname(parent)) {
        if(fs.existsSync(parent)&&(!fs.lstatSync(parent).isDirectory()||fs.lstatSync(parent).isSymbolicLink()))throw Error('Unsafe store path');
        if(parent===path.dirname(parent))break;
      }
      if(!fs.existsSync(dir))return;
      for(const name of fs.readdirSync(dir)) {
        if(!['quorum-source-memory-v1','state.json','ledger.jsonl','quorum.lock','quorum.pending'].includes(name))throw Error('Unrelated store entry');
        const stat=fs.lstatSync(path.join(dir,name));
        if(!stat.isFile()||stat.isSymbolicLink()||stat.nlink!==1)throw Error('Unsafe store entry');
      }
    };
    inspectStore();
    if(request.action==='recall'&&!fs.existsSync(dir)){console.log(JSON.stringify({rows:[],count:0,ledger_entries:0}));process.exit(0);}
    const marker=path.join(dir,'quorum-source-memory-v1');
    if(fs.existsSync(dir)&&(!fs.existsSync(marker)&&fs.readdirSync(dir).length))throw Error('Existing unrelated directory rejected');
    if(fs.existsSync(marker)&&fs.readFileSync(marker,'utf8')!=='quorum-source-memory-v1')throw Error('Invalid store marker');
    fs.mkdirSync(dir,{recursive:true,mode:0o700});
    if(!fs.existsSync(marker))fs.writeFileSync(marker,'quorum-source-memory-v1',{flag:'wx',mode:0o600});
    const lock=path.join(dir,'quorum.lock'),pending=path.join(dir,'quorum.pending');
    const fd=fs.openSync(lock,'wx',0o600);
    try {
      inspectStore();
      if(fs.existsSync(pending))throw Error('Incomplete write needs owner inspection');
      const engine=new HMEM({persistDir:dir,actor:'quorum-source-memory'}),before=engine.ledger.all().length;
      let result;
      if(request.action==='store') {
        fs.writeFileSync(pending,'pending',{flag:'wx',mode:0o600});
        const seen=new Set(engine.store.all().map(m=>m.source));let count=0;
        for(const row of request.rows) {
          const content=JSON.stringify(row),key=crypto.createHash('sha256').update(content).digest('hex');
          if(seen.has(key))continue;
          engine.add({content,source:key,type:'general',layer:'working',confidence:0.7,tags:['candidate-only',row.topic_id,row.docref.source_id],
            provenance:{origin:'model_response',learnedAt:Date.now(),label:'Attributed source memory; fresh verification required',refs:[row.run_id,row.docref.url]}});
          seen.add(key);count++;
        }
        fs.unlinkSync(pending);result={count,rows:[]};
      } else if(request.action==='recall') {
        result={rows:engine.query(request.query,{threshold:0,topN:engine.store.all().length}).memories.map(({memory,relevance})=>({record:JSON.parse(memory.content),memory_id:memory.id,relevance})),count:0};
      } else throw Error('Unsupported action');
      console.log(JSON.stringify({...result,ledger_entries:engine.ledger.all().length-before}));
    } finally {fs.closeSync(fd);fs.unlinkSync(lock);}
  } catch {console.error('H-MEM operation unavailable; private details withheld');process.exitCode=1;}
}
