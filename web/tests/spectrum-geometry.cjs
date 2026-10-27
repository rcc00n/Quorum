const assert = require('node:assert/strict');
const { spectrumGeometry } = require('../lib/spectrum-geometry.ts');
const input = [{id:'TEST-left',score:-1,audience:100},{id:'TEST-center',score:0,audience:1000},{id:'TEST-right',score:1,audience:10000}];
const original = structuredClone(input);
const result = spectrumGeometry(input);
assert.deepEqual(result.points.map(p=>[p.x,p.y]), [[0,100],[50,50],[100,0]]);
assert.deepEqual(result.ticks.map(t=>t.audience),[10000,1000,100]);
assert.deepEqual(input, original);
assert.equal(spectrumGeometry([{id:'TEST',score:.25,audience:1}]).points[0].y,50);
assert.equal(spectrumGeometry([{id:'TEST',score:.25,audience:1}]).points[0].x,62.5);
assert.equal(spectrumGeometry([{id:'TEST',score:-.25,audience:1}]).points[0].x,37.5);
assert.deepEqual(spectrumGeometry([]),{points:[],ticks:[]});
for (const invalid of [{score:NaN,audience:1},{score:Infinity,audience:1},{score:2,audience:1},{score:0,audience:0},{score:0,audience:-1},{score:0,audience:Infinity}])
 assert.equal(spectrumGeometry([{id:'TEST-invalid',...invalid}]).points.length,0);
console.log('PASS: exact rating axis/log audience spacing, equal-audience position, missing/invalid exclusion and immutable input');
