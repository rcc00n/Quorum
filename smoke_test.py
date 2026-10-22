# smoke_test.py: checks your Data (Zetaris) and Power (Nemotron via Meterless/NVIDIA) layers.
# Taken from the Participant Setup Guide (p. 24), with two additions:
#   - the two headers that Meterless Nightshift expects on chat requests
#     (harmless for the NVIDIA route);
#   - the Nightshift Console variable names are accepted alongside the guide's names.
# Reads .env (and .env.local) from the folder you run it in. Never prints secrets.
#
# Install once (inside your virtual environment):
#   pip install openai python-dotenv requests
#
# Run from the project folder while Zetaris (and Nightshift, if used) is running:
#   python smoke_test.py        (Windows)
#   python3 smoke_test.py       (macOS / Linux)

import os
import uuid

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()              # .env in the project folder
load_dotenv(".env.local")  # also accepted, if the team settles on that name
results = []


def setting(*names):
    """First non-empty value among the accepted variable names.

    Canonical names are the Setup Guide's MODEL_BASE_URL / MODEL_API_KEY / NEMOTRON_MODEL
    (the ones in Quorum's .env.example); the Nightshift Console names are accepted too.
    """
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    return None


def check(name, fn):
    try:
        fn()
        results.append(("PASS", name, ""))
    except Exception as error:
        results.append(("FAIL", name, str(error)[:150]))


def need(*names):
    for name in names:
        assert os.environ.get(name), f"{name} is missing from .env"


def zetaris_web():
    url = os.environ.get("ZETARIS_BASE_URL", "http://localhost:3000")
    requests.get(url, timeout=10).raise_for_status()


def zetaris_sql():
    need("ZETARIS_REST_URL", "ZETARIS_ORG_ID", "ZETARIS_API_KEY")
    response = requests.post(
        os.environ["ZETARIS_REST_URL"].rstrip("/") + "/sql-editor/sqls/run",
        headers={
            "Authorization": "Bearer " + os.environ["ZETARIS_API_KEY"],
            "X-Org-ID": os.environ["ZETARIS_ORG_ID"],
            "X-Request-ID": str(uuid.uuid4()),
        },
        json={
            "queryId": str(uuid.uuid4()),
            "sql": "SELECT 1",
            "source": "SqlEditor",
            "limit": 1,
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json().get("data")
    assert data and str(data[0][0]) == "1", "unexpected reply: " + response.text[:80]


def nemotron():
    base_url = setting("MODEL_BASE_URL", "METERLESS_BASE_URL")
    api_key = setting("MODEL_API_KEY", "METERLESS_RUNTIME_TOKEN", "METERLESS_API_KEY")
    model = setting("NEMOTRON_MODEL", "METERLESS_MODEL")
    assert base_url, "MODEL_BASE_URL is missing from .env"
    assert api_key, "MODEL_API_KEY is missing from .env"
    assert model, "NEMOTRON_MODEL is missing from .env"
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        # Required by Meterless Nightshift; ignored by NVIDIA's endpoint.
        default_headers={
            "meterless-app": "hackathon-smoke-test",
            "meterless-scope": "user",
        },
    )
    reply = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
    assert reply.choices, "no reply from the model"


check("Data: Zetaris web interface", zetaris_web)
check("Data: Zetaris runs SQL over its REST API", zetaris_sql)
check("Power: Nemotron replies", nemotron)

for status, name, detail in results:
    print(f"{status} {name} {detail}")
