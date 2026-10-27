"""Offline v4/v6 receipt audit. Never runs reasoning or prints prompts, replies or log text."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100000
REPO = Path(__file__).resolve().parents[1]

class AuditError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise AuditError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def nonfinite(value):
        raise AuditError('nonfinite_json')
    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), 'nonfinite_json')
        return number
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, AuditError):
            raise
        raise AuditError('invalid_json') from None


def checked_inputs(root, manifest):
    root = Path(root).resolve()
    require(not root.is_relative_to(REPO), 'private_inputs_inside_repository')
    require(isinstance(manifest, list) and 1 <= len(manifest) <= 100, 'invalid_manifest')
    files = {}
    for item in manifest:
        require(isinstance(item, dict) and set(item) == {'path', 'size_bytes', 'sha256'}, 'invalid_manifest')
        name = item['path']
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_./-]{1,250}', name), 'invalid_receipt_path')
        parts = PurePosixPath(name)
        require(not parts.is_absolute() and '..' not in parts.parts, 'invalid_receipt_path')
        short = parts.name
        require(short not in files, 'ambiguous_receipt_name')
        require(type(item['size_bytes']) is int and 0 < item['size_bytes'] <= MAX_FILE_BYTES, 'invalid_receipt_size')
        require(isinstance(item['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', item['sha256']), 'invalid_receipt_hash')
        path = root / short
        require(path.is_file() and not path.is_symlink(), 'missing_or_linked_input')
        with path.open('rb') as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
        require(len(raw) == item['size_bytes'] and digest(raw) == item['sha256'], 'input_receipt_mismatch')
        files[short] = raw
    return files


def journal_rows(raw):
    lines = raw.splitlines()
    require(0 < len(lines) <= MAX_ROWS and raw.endswith(b'\n'), 'invalid_journal_framing')
    rows = [strict_json(line) for line in lines]
    for row in rows:
        require(isinstance(row, dict), 'invalid_journal_row')
        require(isinstance(row.get('request_key'), str) and re.fullmatch(r'[0-9a-f]{64}', row['request_key']), 'invalid_request_key')
        require(isinstance(row.get('task'), str) and re.fullmatch(r'[a-z_]{1,40}', row['task']), 'invalid_task')
        require(isinstance(row.get('run_id'), str) and re.fullmatch(r'2026-10-24-russia-ukraine-war-[3-7]', row['run_id']), 'invalid_run_id')
        require(isinstance(row.get('served'), str) and isinstance(row.get('route'), str), 'invalid_model_identity')
        for field in ('ms', 'attempts'):
            require(type(row.get(field)) is int and row[field] >= 0, 'invalid_call_counter')
        # DECISION(2026-10-25, rcc00n/Codex): failed calls may have unknown token usage.
        # Why: missing provider usage is not zero spending; preserve null rather than inventing counts.
        for field in ('tokens_in', 'tokens_out'):
            value = row.get(field)
            require(type(value) is int and value >= 0 or value is None and row['served'] == 'error', 'invalid_call_counter')
        if 'reply' in row:
            require(isinstance(row['reply'], str), 'invalid_reply')
            try:
                require(digest(row['reply'].encode('utf-8')) == row.get('reply_sha256'), 'reply_hash_mismatch')
            except UnicodeError:
                raise AuditError('invalid_reply_encoding') from None
    return rows


def replayable(row):
    return isinstance(row.get('reply'), str) and not row.get('error')


def ledger_matches(ledger, rows, snapshot):
    require(isinstance(ledger, dict) and isinstance(ledger.get('calls'), list), 'invalid_ledger')
    calls = ledger['calls']
    # DECISION(2026-10-25, rcc00n/Codex): compare ordered rows, retaining all duplicate request-key occurrences.
    # Why: deduplicating seeded calls would falsely reconcile historical ledgers and erase FIFO multiplicity.
    projected = [{k: v for k, v in row.items() if k not in ('payload', 'reply')} for row in rows]
    require(calls == projected, 'ledger_journal_mismatch')
    require(isinstance(snapshot, dict) and isinstance(snapshot.get('provenance'), dict), 'invalid_snapshot')
    prov = snapshot['provenance']
    counts = dict(Counter(row['served'] for row in rows))
    require(type(prov.get('model_calls')) is int and prov['model_calls'] == len(rows), 'snapshot_ledger_count_mismatch')
    require(type(prov.get('model_errors')) is int and prov.get('answered_by') == counts
            and prov['model_errors'] == counts.get('error', 0), 'snapshot_model_counts_mismatch')
    require(type(ledger.get('version')) is int and type(snapshot.get('version')) is int, 'invalid_version')
    for field in ('run_id', 'version', 'topic_id', 'edition_date'):
        require(ledger.get(field) == snapshot.get(field), 'ledger_snapshot_identity_mismatch')
    return {'rows': len(rows), 'reply_hashes_checked': sum('reply' in row for row in rows),
            'error_rows': counts.get('error', 0), 'ordered_ledger_identity_verified': True}


REPLAY = re.compile(r'^\s*·\s+([a-z_]+)\s+replayed from journal\s*$')
CALL = re.compile(r'^\s*·\s+([a-z_]+)\s+([a-z_]+)\s+(\S+)\s+(?:(FAILED)\s+)?(\d+)\s+ms(?:\s+(\d+)>(\d+))?')
RESTORE = re.compile(r'^(?:seeding|resuming) (2026-10-24-russia-ukraine-war-[3-7]): (\d+) journalled calls restored into the ledger$')


def parse_log(raw):
    blocks = []
    try:
        lines = raw.decode('utf-8-sig').splitlines()
    except UnicodeError:
        raise AuditError('invalid_log_encoding') from None
    for line in lines:
        found = RESTORE.fullmatch(line)
        if found:
            blocks.append({'run_id': found[1], 'restored': int(found[2]), 'replays': [], 'calls': []})
            continue
        found = REPLAY.fullmatch(line)
        if found:
            require(bool(blocks), 'log_call_before_restore')
            blocks[-1]['replays'].append(found[1])
            continue
        found = CALL.match(line)
        if found:
            require(bool(blocks), 'log_call_before_restore')
            task, lane, model, failed, ms, tin, tout = found.groups()
            require(bool(failed) or tin is not None, 'incomplete_log_call')
            blocks[-1]['calls'].append((task, lane, model, bool(failed), int(ms),
                                       None if failed else int(tin), None if failed else int(tout)))
    require(bool(blocks), 'missing_restore_log')
    return blocks


def session_matches(rows, log_raw, expected_run):
    blocks = parse_log(log_raw)
    reports = []
    for index, block in enumerate(blocks):
        start = block['restored']
        end = blocks[index + 1]['restored'] if index + 1 < len(blocks) else len(rows)
        require(block['run_id'] == expected_run and 0 <= start <= end <= len(rows), 'log_restore_boundary_mismatch')
        live = rows[start:end]
        require(all(row['run_id'] == expected_run for row in live), 'live_run_identity_mismatch')
        expected = [(r['task'], r['lane'], r['route'] if r['served'] == 'error' else r['served'],
                     r['served'] == 'error', r['ms'], None if r['served'] == 'error' else r['tokens_in'],
                     None if r['served'] == 'error' else r['tokens_out']) for r in live]
        require(block['calls'] == expected, 'log_live_rows_mismatch')
        pool = [row for row in rows[:start] if replayable(row)]
        queued = Counter(row['task'] for row in pool)
        replayed = Counter(block['replays'])
        require(not (replayed - queued), 'replay_count_exceeds_queue')
        keys = Counter(row['request_key'] for row in pool)
        reports.append({'restored': start, 'replayable': len(pool), 'replayed': sum(replayed.values()),
                        'live': len(live),
                        'live_ultra': sum(r['served'] == 'nvidia/nemotron-3-ultra-550b-a55b' for r in live),
                        'live_errors': sum(r['served'] == 'error' for r in live),
                        'unused_replayable': len(pool) - sum(replayed.values()),
                        'duplicate_seed_occurrences': len(pool) - len(keys),
                        'live_keys_also_in_seed': sum(r['request_key'] in keys for r in live),
                        'live_log_row_identity_verified': True})
    return reports


def audit_bundle(root, manifest):
    files = checked_inputs(root, manifest)
    def file(name):
        require(name in files, 'missing_required_receipt')
        return files[name]
    journals = {n: journal_rows(file(f'2026-10-24-russia-ukraine-war-{n}.jsonl')) for n in range(3, 8)}
    # The owner dropped exactly the old review_disputed rows when seeding attempt 4.
    require(journals[4][:len(journals[3]) - sum(r['task'] == 'review_disputed' for r in journals[3])]
            == [r for r in journals[3] if r['task'] != 'review_disputed'], 'attempt3_filtered_seed_mismatch')
    for previous, current in ((4, 5), (5, 6), (6, 7)):
        require(file(f'2026-10-24-russia-ukraine-war-{current}.jsonl').startswith(
            file(f'2026-10-24-russia-ukraine-war-{previous}.jsonl')), 'journal_seed_prefix_mismatch')
    versions = {}
    for version, attempt in ((4, 5), (6, 7)):
        ledger = strict_json(file(f'v{version}.ledger.json'))
        snapshot = strict_json(file(f'2026-10-24-closed-v{version}.snapshot.json'))
        require(isinstance(ledger, dict), 'invalid_ledger')
        require(ledger.get('version') == version, 'unexpected_ledger_version')
        versions[str(version)] = ledger_matches(ledger, journals[attempt], snapshot)
        versions[str(version)]['sessions'] = session_matches(journals[attempt], file(f'live_2026-10-24_attempt{attempt}.log'), snapshot['run_id'])
    intermediate = session_matches(journals[6], file('live_2026-10-24_attempt6.log'), '2026-10-24-russia-ukraine-war-6')
    # A task-only replay log cannot identify the consumed request_key or occurrence.
    # DECISION(2026-10-25, rcc00n/Codex): report that limit even when every aggregate matches.
    # Why: FIFO implementation plus aggregate counts is not a per-request consumption receipt.
    return {'report_version': 1, 'checked_input_files': len(files), 'file_integrity_verified': True,
            'seed_lineage_verified': True, 'versions': versions, 'intermediate_attempt6': intermediate,
            'per_key_replay_consumption_verified': False, 'process_config_at_launch_verified': False,
            'provider_execution_verified': False, 'source_text_verified': False, 'published': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args(argv)
    output = Path(args.report).resolve()
    try:
        require(not output.is_relative_to(REPO) and not output.is_relative_to(Path(args.inputs).resolve())
                and not output.exists(), 'report_must_be_new_and_external')
        manifest = strict_json(Path(args.manifest).read_bytes())
        report = audit_bundle(args.inputs, manifest)
        checked_inputs(args.inputs, manifest)  # after parsing, require unchanged original bytes again
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps(report, indent=2) + '\n')
        print('PASS: original receipts, ordered ledger identity, reply hashes and replay aggregates; no execution/publication attestation')
        return 0
    except (AuditError, OSError, TypeError, KeyError, OverflowError):
        print('FAIL: execution receipt audit; private input values withheld')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
