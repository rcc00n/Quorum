"""Canonical FICTIONAL reasoning 1.0 consumer tests, never live integration evidence."""

import copy
import json
import os
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth.models import User
from .reasoning_preview import SAMPLE, load_preview, parse_reasoning, present_reasoning
from .snapshot_validation import SnapshotError, parse_snapshot


def sample():
    return json.loads(SAMPLE.read_bytes())


class ReasoningMappingTests(SimpleTestCase):
    def test_sidecar_binding_is_optional_bounded_and_never_changes_snapshot(self):
        p = sample()
        original = SAMPLE.read_bytes()
        sidecar = dict(snapshot={key: p[key] for key in ("topic_id", "edition_date", "version", "run_id", "status")}, provisional=True,
                       corpus_as_of_utc="2026-10-22T03:53Z", edition_window_utc=[p["window"][key] for key in ("start", "end")],
                       private_evidence={"log": "TEST-private-path-must-not-escape"})
        sidecar["snapshot"]["sha256"] = hashlib.sha256(original).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TEST-sidecar.json"
            with patch.dict(os.environ, {"QUORUM_REASONING_PREVIEW_SIDECAR": str(path)}):
                path.write_text(json.dumps(sidecar))
                result = load_preview(SAMPLE)
                self.assertEqual(result["reasoning"], p)
                self.assertTrue(result["preview"]["corpus_binding"]["provisional"])
                self.assertNotIn("TEST-private-path", json.dumps(result))
                for key, value in (("sha256", "0" * 64), ("run_id", "TEST-wrong-run"), ("version", 99)):
                    bad = copy.deepcopy(sidecar)
                    bad["snapshot"][key] = value
                    path.write_text(json.dumps(bad))
                    with self.subTest(key=key), self.assertRaises(SnapshotError):
                        load_preview(SAMPLE)
                for key, value in (("provisional", "true"), ("corpus_as_of_utc", "TEST-invalid"), ("edition_window_utc", [])):
                    bad = copy.deepcopy(sidecar)
                    bad[key] = value
                    path.write_text(json.dumps(bad))
                    with self.subTest(key=key), self.assertRaises(SnapshotError):
                        load_preview(SAMPLE)

    def test_document_source_identity_is_stable_without_colliding_namespaces(self):
        p = sample()
        evidence = p["stories"][0]["claims"][0]["evidence"]
        evidence.append(copy.deepcopy(evidence[0]))
        first, second = evidence[0], evidence[-1]
        first.update(document_id=777, official_doc_id=None, source_id="TEST-a")
        second.update(document_id=777, official_doc_id=None, source_id="TEST-b")
        with self.assertRaises(SnapshotError):
            parse_reasoning(json.dumps(p).encode())
        second.update(source_id="TEST-a")
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)
        second.update(document_id=None, official_doc_id=777, source_id="TEST-b")
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)
        # Incomplete optional bindings remain unknown, not guessed from another row.
        second.update(source_id=None)
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)

    def test_model_ledger_context_and_original_summary_are_preserved(self):
        p = sample()
        p["provenance"].update(
            fact_checker_model="TEST/ultra",
            model_calls=3,
            answered_by={"TEST/lightning": 2, "TEST/ultra": 1},
            model_errors=0,
        )
        p["stories"][0]["claims"][0]["kind"] = "context"
        # Explicit TEST inconsistency; the consumer must not repair producer prose.
        p["summary"] = "One story crossed the bar. No story crossed the bar today."
        result = present_reasoning(
            json.dumps(p).encode(), now=datetime(2026, 10, 23, 13, tzinfo=timezone.utc)
        )
        self.assertEqual(result["reasoning"], p)
        self.assertEqual(result["digests"][0]["summary"], p["summary"])
        self.assertEqual(result["events"][0]["reasoning"]["claims"][0]["kind"], "context")
        self.assertEqual(result["status"], "demo")
        self.assertFalse(result["preview"]["published"])
        self.assertEqual(result["preview"]["expiry_hint"], "expired")

    def test_invalid_model_ledger_rejected_without_weakening_old_envelope(self):
        mutations = [
            {"model_calls": True},
            {"model_calls": -1},
            {"model_calls": 100001},
            {"model_errors": 1.5},
            {"model_errors": 4},
            {"answered_by": []},
            {"answered_by": {"": 3}},
            {"answered_by": {"TEST/lightning": True}},
            {"answered_by": {"TEST/lightning": 0}},
            {"answered_by": {"TEST/lightning": 2}},
            {"answered_by": {"TEST/lightning": 2, "error": 1}},
            {"fact_checker_model": ""},
            {"fact_checker_model": None},
            {"unknown_model_field": "TEST"},
        ]
        for mutation in mutations:
            p = sample()
            p["provenance"].update(
                fact_checker_model="TEST/ultra",
                model_calls=3,
                answered_by={"TEST/lightning": 3},
                model_errors=0,
            )
            p["provenance"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(SnapshotError):
                parse_reasoning(json.dumps(p).encode())
        p = sample()
        p["provenance"].update(
            model_calls=3, model_errors=1,
            answered_by={"TEST/lightning": 2, "error": 1},
        )
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)

    def test_exact_sample_and_no_forged_provenance(self):
        raw = SAMPLE.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "2dd7510a618c584ee3925efb9de3c745417a6abe549a10f3042271ce22ab0366",
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

    def test_three_exact_canonical_fixtures(self):
        cases = [
            (
                "snapshot.sample.json",
                "2dd7510a618c584ee3925efb9de3c745417a6abe549a10f3042271ce22ab0366",
                "available",
                2,
                45,
            ),
            (
                "snapshot.empty-day.sample.json",
                "014cc695491181a61012559aeb97ddd878938571b21bb749597bc55190ea97e7",
                "available",
                0,
                29,
            ),
            (
                "snapshot.partial.sample.json",
                "df0c03e5903b5dd2238eb03233a10f25ac0515e6a3ed65ea4d059b1de1769495",
                "partial",
                2,
                45,
            ),
        ]
        for name, digest, status, stories, trace in cases:
            with self.subTest(name=name):
                raw = SAMPLE.with_name(name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
                result = present_reasoning(raw)
                self.assertEqual(result["reasoning"], json.loads(raw))
                self.assertEqual(result["preview"]["status"], status)
                self.assertFalse(result["preview"]["published"])
                self.assertIsNone(result["reasoning"]["published_at"])
                self.assertEqual(len(result["events"]), stories)
                self.assertEqual(len(result["reasoning"]["trace"]), trace)
                with self.assertRaises(SnapshotError):
                    parse_snapshot(raw)

    def test_envelope_timestamps_null_publication_and_expiry(self):
        p = sample()
        raw = json.dumps(p).encode()
        before = present_reasoning(
            raw, now=datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        )
        after = present_reasoning(
            raw, now=datetime(2026, 10, 23, 13, tzinfo=timezone.utc)
        )
        self.assertEqual(before["preview"]["expiry_hint"], "within_hint")
        self.assertEqual(after["preview"]["expiry_hint"], "expired")
        self.assertFalse(before["preview"]["published"])
        self.assertFalse(after["preview"]["published"])
        # Even self-declared live provenance and publication cannot activate preview publication.
        p["provenance"] = dict(
            corpus="zetaris", model="meterless/auto", fictional=False
        )
        p["published_at"] = "2026-10-23T04:20:00Z"
        result = present_reasoning(json.dumps(p).encode())
        self.assertFalse(result["preview"]["published"])
        self.assertEqual(result["status"], "demo")
        self.assertFalse(result["reasoning"]["provenance"]["fictional"])
        self.assertIn("Producer-declared collected corpus", result["preview"]["warnings"][0])
        self.assertIn("not publication-approved", result["preview"]["warnings"][0])
        p["provenance"]["model"] = "stand-ins"
        result = present_reasoning(json.dumps(p).encode())
        self.assertIn("no AI verification", result["preview"]["warnings"][0])
        self.assertFalse(result["preview"]["published"])

    def test_current_optional_access_and_roundup_audit_contract(self):
        p = sample()
        evidence = p["stories"][0]["claims"][0]["evidence"][0]
        evidence["by_headline"] = True
        item = p["roundup"]["groups"][0]["items"][0]
        item["line_source"] = "title"
        p["trace"][0]["detail"] = [{"text": "TEST dropped claim", "reason": "TEST origin mismatch"}]
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)
        for value in ("full-text", 1, None):
            evidence["by_headline"] = value
            with self.assertRaises(SnapshotError):
                parse_reasoning(json.dumps(p).encode())
        evidence["by_headline"] = True
        item["line_source"] = "invented"
        with self.assertRaises(SnapshotError):
            parse_reasoning(json.dumps(p).encode())
        item["line_source"] = "model"
        p["trace"][0]["detail"][0]["private_prompt"] = "TEST rejected"
        with self.assertRaises(SnapshotError):
            parse_reasoning(json.dumps(p).encode())

    def test_latest_quote_binding_and_third_review_declarations(self):
        p = sample()
        c = p["stories"][0]["claims"][0]
        c.update(reviewer_status=c["status"], reviewer_reason="TEST review", reviewer_quote="TEST decisive words", resolved_by="reviewer")
        e = c["evidence"][0]
        e.update(source_id="TEST-source", document_id=None, official_doc_id=42,
                 char_start=4, char_end=4 + len(e["quote"]), content_hash_at_quote="a" * 64,
                 access_achieved=1, fetched_at="2026-10-23T04:00:00Z", hash_mismatch=False,
                 from_previous_day=True)
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)
        for change in ({"document_id": 42}, {"official_doc_id": True}, {"official_doc_id": None},
                       {"char_start": -1}, {"char_end": 4}, {"char_start": None},
                       {"content_hash_at_quote": "not-a-hash"}, {"access_achieved": True},
                       {"access_achieved": 3}, {"fetched_at": "2026-10-23"},
                       {"hash_mismatch": "false"}, {"from_previous_day": None}):
            q = copy.deepcopy(p)
            q["stories"][0]["claims"][0]["evidence"][0].update(change)
            with self.subTest(change=change), self.assertRaises(SnapshotError):
                parse_reasoning(json.dumps(q).encode())
        e.update(char_start=None, char_end=None, content_hash_at_quote=None,
                 access_achieved=None, fetched_at=None, hash_mismatch=None)
        self.assertEqual(parse_reasoning(json.dumps(p).encode()), p)
        p.update(summary_source="fallback", status="partial", errors=[dict(node="publish", event_id=None, message="TEST summary rejected")])
        self.assertEqual(present_reasoning(json.dumps(p).encode())["preview"]["status"], "partial")
        p["summary_source"] = "invented"
        with self.assertRaises(SnapshotError):
            parse_reasoning(json.dumps(p).encode())

    def test_dst_calendar_windows(self):
        for day, start, end, expires in [
            (
                "2026-03-08",
                "2026-03-07T10:30:00Z",
                "2026-03-08T09:30:00Z",
                "2026-03-09T12:00:00Z",
            ),
            (
                "2026-11-01",
                "2026-10-31T09:30:00Z",
                "2026-11-01T10:30:00Z",
                "2026-11-02T13:00:00Z",
            ),
        ]:
            p = sample()
            p.update(
                edition_date=day, window=dict(start=start, end=end), expires_at=expires
            )
            parse_reasoning(json.dumps(p).encode())

    def test_invalid_envelope_and_private_partial_errors(self):
        mutations = [
            lambda p: p.pop("generated_at"),
            lambda p: p.update(generated_at="2026-02-31T01:00:00Z"),
            lambda p: p.update(generated_at="2026-10-23T01:00:00"),
            lambda p: p.update(published_at="2026-10-20T00:00:00Z"),
            lambda p: p.update(expires_at="2026-10-20T00:00:00Z"),
            lambda p: p.update(edition_timezone="Unknown/Zone"),
            lambda p: p["window"].update(start=p["window"]["end"]),
            lambda p: p["provenance"].update(fictional="false"),
            lambda p: p.update(
                errors=[dict(node="frame", event_id="unknown", message="error")]
            ),
            lambda p: p.update(
                errors=[
                    dict(
                        node="frame",
                        event_id=None,
                        message="error",
                        traceback="private",
                    )
                ]
            ),
        ]
        for i, mutation in enumerate(mutations):
            p = sample()
            mutation(p)
            with self.subTest(i=i), self.assertRaises(SnapshotError):
                parse_reasoning(json.dumps(p).encode())
        p = sample()
        private = "TEST private internal endpoint https://example.com/?credential=private-value"
        p.update(
            status="partial",
            errors=[
                dict(
                    node="frame", event_id=p["stories"][0]["event_id"], message=private
                ),
                private,
            ],
        )
        result = present_reasoning(json.dumps(p).encode())
        self.assertNotIn(private, json.dumps(result))
        self.assertIn("internal details withheld", json.dumps(result))
        self.assertEqual(result["preview"]["status"], "partial")

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

    def test_all_canonical_samples_through_authenticated_api(self):
        self.client.force_login(self.reader)
        for name in (
            "snapshot.sample.json",
            "snapshot.empty-day.sample.json",
            "snapshot.partial.sample.json",
        ):
            with self.subTest(name=name), patch.dict(
                os.environ,
                {
                    "QUORUM_ENABLE_REASONING_PREVIEW": "1",
                    "QUORUM_REASONING_PREVIEW_FILE": str(SAMPLE.with_name(name)),
                },
            ):
                response = self.client.get(
                    "/api/preview/reasoning/", HTTP_HOST="localhost"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json()["reasoning"],
                    json.loads(SAMPLE.with_name(name).read_bytes()),
                )
                self.assertFalse(response.json()["preview"]["published"])

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
