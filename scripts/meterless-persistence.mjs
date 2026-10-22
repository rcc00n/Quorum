// Infrastructure smoke check only. Imports the unmodified official references.
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const root = process.env.METERLESS_HOME;
const { HMEM } = await import(pathToFileURL(join(root, 'engines/hmem/reference/src/index.ts')));
const { WorldModel } = await import(pathToFileURL(join(root, 'engines/world-model/reference/src/index.ts')));
const dir = mkdtempSync(join(tmpdir(), 'quorum-memory-'));
try {
  const persistDir = join(dir, 'memory');
  const memory = new HMEM({ persistDir });
  const record = memory.add({ content: 'environment persistence sentinel', source: 'setup-smoke' });
  const restored = new HMEM({ persistDir });
  assert.equal(restored.store.get(record.id)?.content, record.content);
  assert.ok(restored.ledger.history(record.id).some(x => x.action === 'create'));
  const options = { namespace: 'setup', storage: 'local', directory: join(dir, 'world') };
  const world = new WorldModel(options);
  const recordState = await world.upsertEntity({ type: 'setup', name: 'persistence sentinel', attrs: { marker: 'saved' }, source: { kind: 'setup-smoke', at: '2026-01-01T00:00:00Z' } });
  const next = new WorldModel(options);
  assert.equal(next.view('graph').entity(recordState.id)?.attrs.marker, 'saved');
  assert.equal(next.view('graph').entity(recordState.id)?.name, 'persistence sentinel');
  console.log('PASS memory, audit ledger and World Model JSON persistence');
} finally { rmSync(dir, { recursive: true, force: true }); }
