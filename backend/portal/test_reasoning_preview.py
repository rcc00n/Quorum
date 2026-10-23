"""Canonical FICTIONAL reasoning 1.0 consumer tests, never live integration evidence."""

import copy
import json
import os
import hashlib
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth.models import User
from .reasoning_preview import SAMPLE, load_preview, parse_reasoning, present_reasoning
from .snapshot_validation import SnapshotError, parse_snapshot


def sample():
    return json.loads(SAMPLE.read_bytes())


class ReasoningMappingTests(SimpleTestCase):
    def test_exact_sample_and_no_forged_provenance(self):
        raw = SAMPLE.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "4662e8aa1616f39cad3663ce2963aaf9eec0eac82929b1637d6419168a7287d1",
        )
        result = present_reasoning(raw)
        self.assertEqual(result["reasoning"], json.loads(raw))
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(len(result["reasoning"]["trace"]), 45)
        self.assertEqual(result["status"], "demo")
        self.assertFalse(result["preview"]["published"])
        self.assertNotIn("publication", result)
        for event in result["events"]:
            self.assertNotIn(
                "analysis", event
            )  # No invented IDs, hashes, offsets or review times.
            self.assertEqual(event["id"], event["reasoning"]["event_id"])
            self.assertTrue(
                all(
                    s["allsides"] is None and s["audience"] is None
                    for s in event["sources"]
                )
            )
        with self.assertRaises(SnapshotError):
            parse_snapshot(raw)

    def test_context_is_not_promoted_and_speakers_stay_attributed(self):
        p = sample()
        s = p["stories"][0]
        s["article"].append(
            dict(
                kind="context",
                text="TEST unverified context",
                claim_ids=[s["claims"][-1]["id"]],
                sources=[s["sources"][0]],
            )
        )
        mapped = present_reasoning(json.dumps(p).encode())
        self.assertEqual(
            mapped["events"][0]["reasoning"]["article"][-1]["kind"], "context"
        )
        self.assertFalse(
            any(
                x["text"] == "TEST unverified context"
                for x in mapped["events"][0]["established"]
            )
        )
        statement = next(c for c in s["claims"] if c.get("kind") == "statement")
        self.assertTrue(
            any(
                e["text"] == statement["text"]
                for e in mapped["events"][0]["statements"]
            )
        )

    def test_bad_input_references_versions_urls_structures(self):
        mutations = [
            lambda p: p.update(schema_version="2.0"),
            lambda p: p.update(edition_date="2026-02-31"),
            lambda p: p.update(status="error"),
            lambda p: p.update(secret="private"),
            lambda p: p["stories"][0]["claims"][0]["evidence"][0].update(
                url="javascript:alert(1)"
            ),
            lambda p: p["stories"][0]["claims"][0]["evidence"][0].update(
                url="https://127.0.0.1/"
            ),
            lambda p: p["stories"][0]["article"][0].update(claim_ids=["missing"]),
            lambda p: p["stories"][0]["rubric"].update(total=1),
            lambda p: p["stories"][0]["claims"][0].update(status="disputed"),
            lambda p: p["stories"][0]["claims"][0].update(kind="statement"),
            lambda p: p["stories"][0]["spectrum"]["coverage"].update(major_left=[4, 2]),
            lambda p: p["trace"][0].update(event_id="missing"),
            lambda p: p["trace"][0].update(event_id=[]),
            lambda p: p["trace"][0].update(duration_ms=float("nan")),
            lambda p: p["stories"].append(copy.deepcopy(p["stories"][0])),
        ]
        for mutation in mutations:
            p = sample()
            mutation(p)
            with self.subTest(mutation=mutations.index(mutation)), self.assertRaises(
                SnapshotError
            ):
                parse_reasoning(json.dumps(p).encode())
        for raw in (
            b"{}",
            b'{"a":1,"a":2}',
            b"[" * 30 + b"0" + b"]" * 30,
            b" " * (2 * 1024 * 1024 + 1),
        ):
            with self.assertRaises(SnapshotError):
                parse_reasoning(raw)

    def test_missing_optional_trace_and_partial_empty(self):
        p = sample()
        p.pop("trace")
        p["status"] = "partial"
        p["errors"] = ["TEST upstream unavailable"]
        mapped = present_reasoning(json.dumps(p).encode())
        self.assertEqual(mapped["preview"]["status"], "partial")
        self.assertNotIn("trace", mapped["reasoning"])
        p.update(status="empty", stories=[], trace=[], errors=[])
        p["roundup"]["empty_day"] = True
        self.assertEqual(present_reasoning(json.dumps(p).encode())["events"], [])


@override_settings(
    DEBUG=True, ALLOWED_HOSTS=["localhost", "testserver", "quorum.raccncode.com"]
)
class ReasoningPreviewAPITests(TestCase):
    def setUp(self):
        self.reader = User.objects.create_user("TEST-preview-reader")

    def test_opt_in_session_localhost_and_no_production_fallback(self):
        path = "/api/preview/reasoning/"
        with patch.dict(os.environ, {"QUORUM_ENABLE_REASONING_PREVIEW": "0"}):
            self.assertEqual(
                self.client.get(path, HTTP_HOST="localhost").status_code, 404
            )
        with patch.dict(
            os.environ,
            {
                "QUORUM_ENABLE_REASONING_PREVIEW": "1",
                "QUORUM_REASONING_PREVIEW_FILE": "",
            },
        ):
            self.assertEqual(
                self.client.get(path, HTTP_HOST="localhost").status_code, 401
            )
            self.client.force_login(self.reader)
            response = self.client.get(path, HTTP_HOST="localhost")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(len(response.json()["reasoning"]["trace"]), 45)
            self.assertEqual(
                self.client.get(path, HTTP_HOST="quorum.raccncode.com").status_code, 404
            )
            for directory in ("/var/lib/quorum", "/var/lib/quorum/preview"):
                with self.settings(DATA_DIR=Path(directory)):
                    self.assertEqual(
                        self.client.get(path, HTTP_HOST="localhost").status_code, 404
                    )
            with patch.dict(
                os.environ, {"QUORUM_REASONING_PREVIEW_FILE": "/nonexistent/TEST.json"}
            ):
                failed = self.client.get(path, HTTP_HOST="localhost")
                self.assertEqual(failed.status_code, 422)
                self.assertNotIn("TEST.json", failed.content.decode())
            with self.settings(DEBUG=False):
                self.assertEqual(
                    self.client.get(path, HTTP_HOST="localhost").status_code, 404
                )
            self.assertEqual(
                self.client.post(path, HTTP_HOST="localhost").status_code, 405
            )
            self.assertEqual(
                self.client.get(
                    path + "?version=999", HTTP_HOST="localhost"
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.get(
                    path + "?date=2026-10-23", HTTP_HOST="localhost"
                ).status_code,
                404,
            )
            ordinary = self.client.get("/api/feed/", HTTP_HOST="localhost").json()
            self.assertNotEqual(ordinary["status"], "demo")
            self.assertEqual(ordinary["events"], [])
            self.assertEqual(
                self.client.get("/staff/", HTTP_HOST="localhost").status_code, 302
            )
