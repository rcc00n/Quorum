"""Read-only private-file acceptance. Never opens the snapshot store or calls a provider."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from portal.reasoning_preview import artifact_review_issues, bind_preview_sidecar, parse_preview_json, present_reasoning
from portal.snapshot_store import read_bounded
from portal.snapshot_validation import SnapshotError


def require(ok, code):
    if not ok:
        raise SnapshotError(code)


class Command(BaseCommand):
    help = 'Validate original reasoning bytes and sidecar metadata locally; no publication or execution attestation.'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True)
        parser.add_argument('--sha256', required=True)
        parser.add_argument('--sidecar', required=True)
        parser.add_argument('--sidecar-sha256', required=True)
        parser.add_argument('--producer-commit', required=True)

    def handle(self, *args, **options):
        report = dict(report_version=1, compatible=False, metadata_valid=False,
                      execution_verified=False, source_text_verified=False, published=False, issues=[])
        try:
            for key in ('sha256', 'sidecar_sha256'):
                require(re.fullmatch(r'[0-9a-f]{64}', options[key]), 'expected_full_sha256_required')
            commit = options['producer_commit']
            require(re.fullmatch(r'[0-9a-f]{40}', commit), 'expected_full_producer_commit_required')
            raw, sidecar_raw = (read_bounded(Path(options[k])) for k in ('file', 'sidecar'))
            require(hashlib.sha256(raw).hexdigest() == options['sha256'], 'snapshot_sha256_mismatch')
            require(hashlib.sha256(sidecar_raw).hexdigest() == options['sidecar_sha256'], 'sidecar_sha256_mismatch')
            result = present_reasoning(raw)
            bind_preview_sidecar(sidecar_raw, raw, result)
            p = result['reasoning']
            require(p['provenance']['fictional'] is False and p['provenance']['model'] != 'stand-ins'
                    and p['provenance'].get('model_calls', 0) > 0, 'genuine_model_output_required')
            report.update(compatible=True, snapshot_sha256=options['sha256'], sidecar_sha256=options['sidecar_sha256'],
                          status=p['status'], stories=len(p['stories']), roundup=p['roundup']['count'],
                          trace_rows=len(p.get('trace', [])), errors=len(p.get('errors', [])),
                          provisional=result['preview']['provisional'])
            sidecar = parse_preview_json(sidecar_raw)
            producer = sidecar['producer']
            if 'commit_of_the_publishing_process' in producer:
                require(commit.startswith(producer['commit_of_the_publishing_process']), 'producer_commit_mismatch')
                try:
                    config = subprocess.check_output(['git', 'show', f'{commit}:reasoning/config/reasoning.toml'],
                        cwd=Path(__file__).resolve().parents[4], stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    raise SnapshotError('producer_config_unavailable') from None
                report.update(producer_commit=commit, git_config_sha256=hashlib.sha256(config).hexdigest(),
                              git_config_crlf_sha256=hashlib.sha256(config.replace(b'\n', b'\r\n')).hexdigest())
                # Prefixes plus a reproduction command are not a full original config attestation.
                report['issues'].extend(['producer_config_hash_incomplete'] + artifact_review_issues(options['sha256'], p['run_id']))
                self.stdout.write(json.dumps(report, sort_keys=True))
                raise CommandError('Reasoning acceptance blocked; inspect safe report codes', returncode=1)
            prefix = re.match(r'^([0-9a-f]{7,40})(?:\s|$)', producer['commit'])
            require(prefix is not None and commit.startswith(prefix[1]), 'producer_commit_mismatch')
            declared = producer['config_sha256']
            require(isinstance(declared, str) and re.fullmatch(r'[0-9a-f]{64}', declared), 'invalid_config_sha256')
            # DECISION(2026-10-24, rcc00n/Codex): compare local Git bytes, never repair the sidecar or fetch a corpus.
            # Why: metadata compatibility is separate from independently verified execution and publication.
            try:
                config = subprocess.check_output(['git', 'show', f'{commit}:reasoning/config/reasoning.toml'],
                                                 cwd=Path(__file__).resolve().parents[4], stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                raise SnapshotError('producer_config_unavailable') from None
            actual = hashlib.sha256(config).hexdigest()
            report.update(producer_commit=commit, declared_config_sha256=declared, git_config_sha256=actual)
            require(actual == declared, 'producer_config_mismatch')
            report['metadata_valid'] = True
            report['issues'].extend(artifact_review_issues(options['sha256'], p['run_id']))
        except SnapshotError as exc:
            report['issues'].append(str(exc))
        except (OSError, ValueError, TypeError, KeyError):
            report['issues'].append('acceptance_input_unavailable_or_invalid')
        self.stdout.write(json.dumps(report, sort_keys=True))
        if report['issues']:
            raise CommandError('Reasoning acceptance blocked; inspect safe report codes', returncode=1)
