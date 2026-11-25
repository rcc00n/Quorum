# Offline reviewer guide

This path needs no provider credentials, sponsor runtime, production database or
public demo. Start from a fresh clone; do not copy a service `.env` into it.
Package installation needs normal registry access. The review itself uses bundled
fictional evidence. Python 3.11+ and Node 22 are the supported local combination.

## 1. Create an isolated environment

From the repository root:

```bash
python3 -m venv /tmp/quorum-review-venv
. /tmp/quorum-review-venv/bin/activate
python -m pip install -r backend/requirements.txt -e './reasoning[dev]'
export QUORUM_PORTAL_DATA="$(mktemp -d /tmp/quorum-review-data.XXXXXX)"
export DJANGO_DEBUG=1
bash scripts/doctor.sh --offline
bash scripts/verify-all.sh --offline
```

The diagnostics explicitly leave external integrations BLOCKED in offline mode;
exit code 2 means those integrations were not exercised, not that they passed.
The directory is temporary local review data, not an operational store. Private
review paths must be outside every Git checkout. If `/tmp` itself is a checkout on
your machine, choose a clean temporary root (for example `/var/tmp`) and pass
`--basetemp /var/tmp/quorum-review-pytest` to pytest.

## 2. Follow a synthetic investigation

```bash
python -m quorum_reasoning.run --dry-run --quiet --out "$QUORUM_PORTAL_DATA/editions"
python -m pytest reasoning/tests
python backend/manage.py test portal
python backend/manage.py makemigrations --check --dry-run
```

Open the generated versioned JSON under `editions/`: compare claims, evidence,
verdicts, articles, roundup and trace with
[`snapshot.sample.json`](examples/snapshot.sample.json). `provenance.fictional`
and dry-model labels are intentional. The graph executes; real collection and
provider inference do not. Do not substitute `--model live`, `--models` or
`--test-connection` for these commands: those belong to separately configured
integration work and can use provider credits.

## 3. Optional browser preview

```bash
export QUORUM_PYTHON="$(command -v python)"
export QUORUM_WEB_BUILD="$(mktemp -d /tmp/quorum-review-web.XXXXXX)"
bash deploy/build-web.sh
node web/tests/boundary.cjs --reasoning --serve
```

Although the build helper lives under `deploy/`, this command only installs/builds
locally. The boundary harness starts Django and Next on available loopback ports,
creates synthetic accounts in its own temporary database, and prints the local
preview URL and path to a private local credential file. Open that file locally,
sign in, and inspect `/preview/reasoning`. Never publish the credential file.
No production login or publisher is used. Ctrl+C shuts down the harness and removes
its temporary account data. Your separate build/review directories remain yours
to remove when finished.

## Suggested reading order

- [`reasoning/quorum_reasoning/graph.py`](../reasoning/quorum_reasoning/graph.py):
  bounded graph transitions and ownership of evidence state.
- [`backend/portal/reasoning_preview.py`](../backend/portal/reasoning_preview.py):
  typed boundary and honesty labels for input evidence.
- [`backend/portal/reasoning_editions.py`](../backend/portal/reasoning_editions.py):
  immutable installed files and integrity failures.
- [`web/README.md`](../web/README.md): reader navigation and UI contract.
- [Project decisions](DECISIONS.md): why these constraints exist.

The current owner/role map is in the [root README](../README.md#team-and-attribution).
No setup command in this guide starts or deploys a hosted service.
