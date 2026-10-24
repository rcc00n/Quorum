const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {verifyEvidence,externalNewOutput,captions}=require('./demo_tour.cjs');
assert.throws(()=>verifyEvidence(Buffer.from('{"fictional":false}'),Buffer.from('TEST')),/Original snapshot required/);
assert.throws(()=>externalNewOutput('relative/TEST'));
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'quorum-demo-test-'));
try {
  assert.throws(()=>externalNewOutput(temp));
  fs.mkdirSync(path.join(temp,'.git'));assert.throws(()=>externalNewOutput(path.join(temp,'TEST-output')),/outside repositories/);
} finally {fs.rmSync(temp,{recursive:true});}
assert.ok(captions().startsWith('WEBVTT\n'));
assert.ok(captions().includes('03:50.000'));
assert.ok(captions().includes('config digest discrepancy blocks'));
assert.ok(captions().includes('do not prove the full workflow'));
console.log('PASS: demo rejects substitutes/repository outputs and labels blocked sponsor/provenance claims');
