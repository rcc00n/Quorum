"""Read-only private-file acceptance; with --install, the accepted bytes are copied into the reader's directory.
Never opens the snapshot store or calls a provider."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from portal.reasoning_preview import artifact_review_issues, bind_preview_sidecar, parse_preview_json, present_reasoning
from portal.reasoning_editions import ROOT
from portal.snapshot_store import read_bounded
from portal.snapshot_validation import SnapshotError


def require(ok, code):
    if not ok:
        raise SnapshotError(code)


def write_private(path, data):
    """Write bytes next to the target under a temporary name with mode 0600, then rename into place."""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def producer_config(options, commit):
    """The producer's reasoning.toml bytes: from --producer-config when given, else from the local Git history."""
    if options.get('producer_config'):
        return read_bounded(Path(options['producer_config']))
    try:
        return subprocess.check_output(['git', 'show', f'{commit}:reasoning/config/reasoning.toml'],
                                       cwd=Path(__file__).resolve().parents[4], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        raise SnapshotError('producer_config_unavailable') from None


def install(raw, sidecar_raw, p, options, report):
    """Copy the accepted edition into QUORUM_REASONING_EDITIONS_ROOT/<topic>/<date>/v<N>.*; versions are immutable."""
    root = os.getenv(ROOT, '')
    require(bool(root), 'editions_root_not_configured')
    base = Path(root)
    require(base.is_absolute() and base.is_dir(), 'editions_root_unavailable')
    folder = base / p['topic_id'] / p['edition_date']
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / f"v{p['version']}.json"
    require(not target.exists(), 'edition_version_already_installed')
    meta = dict(
        installed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        snapshot_sha256=options['sha256'],
        sidecar_sha256=options['sidecar_sha256'],
        producer_commit=options['producer_commit'],
        topic_id=p['topic_id'],
        edition_date=p['edition_date'],
        version=p['version'],
        run_id=p['run_id'],
        fictional=p['provenance']['fictional'],
    )
    write_private(folder / f"v{p['version']}.sidecar.json", sidecar_raw)
    write_private(folder / f"v{p['version']}.meta.json", json.dumps(meta, sort_keys=True).encode())
    write_private(target, raw)
    report.update(installed=True, installed_version=p['version'], installed_at=meta['installed_at'])


class Command(BaseCommand):
    help = ('Validate original reasoning bytes and sidecar metadata locally; no publication or execution attestation. '
            '--install copies an accepted edition into the login-only reader\'s directory.')

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True)
        parser.add_argument('--sha256', required=True)
        parser.add_argument('--sidecar', required=True)
        parser.add_argument('--sidecar-sha256', required=True)
        parser.add_argument('--producer-commit', required=True)
        # DECISION(2026-10-26, Anastasia/Claude Code): --install is the only write this command makes, into the
        # reader's root (portal/reasoning_editions.py) and only after a clean acceptance; --allow-fictional, like
        # portal_snapshot's --allow-demo, works in DEBUG only, so a developer can rehearse with the bundled sample.
        # Why: Yelysei's hand-over plan (Issue #2 comment 6426106426) installs the edition files after the cut.
        parser.add_argument('--install', action='store_true')
        parser.add_argument('--allow-fictional', action='store_true')
        # DECISION(2026-10-26, Anastasia/Claude Code; Yelysei's review of PR #31): a VPS release is a tarball
        # without .git, so --producer-config names the producer's reasoning/config/reasoning.toml bytes to
        # hash instead of `git show`; the declared sha256 in the sidecar must still match. Why: otherwise every
        # install on the VPS fails with producer_config_unavailable.
        parser.add_argument('--producer-config')

    def handle(self, *args, **options):
        report = dict(report_version=1, compatible=False, metadata_valid=False,
                      execution_verified=False, source_text_verified=False, published=False, issues=[])
        raw = sidecar_raw = p = None
        try:
            for key in ('sha256', 'sidecar_sha256'):
                require(re.fullmatch(r'[0-9a-f]{64}', options[key]), 'expected_full_sha256_required')
            commit = options['producer_commit']
            require(re.fullmatch(r'[0-9a-f]{40}', commit), 'expected_full_producer_commit_required')
            require(not options['allow_fictional'] or settings.DEBUG, 'allow_fictional_requires_debug')
            raw, sidecar_raw = (read_bounded(Path(options[k])) for k in ('file', 'sidecar'))
            require(hashlib.sha256(raw).hexdigest() == options['sha256'], 'snapshot_sha256_mismatch')
            require(hashlib.sha256(sidecar_raw).hexdigest() == options['sidecar_sha256'], 'sidecar_sha256_mismatch')
            result = present_reasoning(raw)
            bind_preview_sidecar(sidecar_raw, raw, result)
            p = result['reasoning']
            genuine = (p['provenance']['fictional'] is False and p['provenance']['model'] != 'stand-ins'
                       and p['provenance'].get('model_calls', 0) > 0)
            require(genuine or options['allow_fictional'], 'genuine_model_output_required')
            report.update(compatible=True, snapshot_sha256=options['sha256'], sidecar_sha256=options['sidecar_sha256'],
                          status=p['status'], stories=len(p['stories']), roundup=p['roundup']['count'],
                          trace_rows=len(p.get('trace', [])), errors=len(p.get('errors', [])),
                          provisional=result['preview']['provisional'], fictional=p['provenance']['fictional'])
            sidecar = parse_preview_json(sidecar_raw)
            producer = sidecar['producer']
            if 'commit_of_the_publishing_process' in producer:
                prefix = producer['commit_of_the_publishing_process']
                require(isinstance(prefix, str) and re.fullmatch(r'[0-9a-f]{7,40}', prefix)
                        and commit.startswith(prefix), 'producer_commit_mismatch')
                config = producer_config(options, commit)
                report.update(producer_commit=commit, git_config_sha256=hashlib.sha256(config).hexdigest(),
                              git_config_crlf_sha256=hashlib.sha256(config.replace(b'\n', b'\r\n')).hexdigest())
                # DECISION(2026-10-25, rcc00n/Codex): compare both complete LF/CRLF declarations for v5/v6.
                # Why: matching config metadata is useful but cannot prove execution or lift the v4 impact hold.
                declared = [producer.get(key) for key in ('config_sha256_git_blob_lf', 'config_sha256_working_copy_crlf')]
                if all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) for value in declared):
                    require(declared == [report['git_config_sha256'], report['git_config_crlf_sha256']], 'producer_config_mismatch')
                    report['metadata_valid'] = True
                else:
                    report['issues'].append('producer_config_hash_incomplete')
                report['issues'].extend(artifact_review_issues(options['sha256'], p['run_id']))
            else:
                prefix = re.match(r'^([0-9a-f]{7,40})(?:\s|$)', producer['commit'])
                require(prefix is not None and commit.startswith(prefix[1]), 'producer_commit_mismatch')
                declared = producer['config_sha256']
                require(isinstance(declared, str) and re.fullmatch(r'[0-9a-f]{64}', declared), 'invalid_config_sha256')
                # DECISION(2026-10-24, rcc00n/Codex): compare local Git bytes, never repair the sidecar or fetch a corpus.
                # Why: metadata compatibility is separate from independently verified execution and publication.
                config = producer_config(options, commit)
                actual = hashlib.sha256(config).hexdigest()
                report.update(producer_commit=commit, declared_config_sha256=declared, git_config_sha256=actual)
                require(actual == declared, 'producer_config_mismatch')
                report['metadata_valid'] = True
                report['issues'].extend(artifact_review_issues(options['sha256'], p['run_id']))
            if options['install'] and not report['issues']:
                install(raw, sidecar_raw, p, options, report)
        except SnapshotError as exc:
            report['issues'].append(str(exc))
        except (OSError, ValueError, TypeError, KeyError):
            report['issues'].append('acceptance_input_unavailable_or_invalid')
        self.stdout.write(json.dumps(report, sort_keys=True))
        if report['issues']:
            raise CommandError('Reasoning acceptance blocked; inspect safe report codes', returncode=1)
