"""Proposal/fixture correctness tests only; never evidence of sponsor integration."""

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from .snapshot_validation import (
    MAX_BYTES,
    SnapshotError,
    parse_snapshot,
    validate_snapshot,
)
from .snapshot_store import SnapshotStore, read_bounded
from .snapshot_projection import project
from .integration import PublishedAdapter

FIXTURE = Path(__file__).parent / "fixtures/analysis-demo.json"
CLOCK = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)


def sample():
    return json.loads(FIXTURE.read_text())


class ValidationTests(SimpleTestCase):
    def test_demo_and_unknown_nulls(self):
        p = validate_snapshot(sample())
        self.assertEqual(p["mode"], "demo")
        self.assertEqual(p["events"][0]["analysis"]["claims"][-1]["status"], "unknown")
        self.assertIsNone(p["sources"][0]["audience"])
        projected = project(p, {"status": "partial", "revision": "demo-r1"})
        self.assertEqual(projected["status"], "demo")
        self.assertEqual(len(projected["events"][0]["established"]), 1)
        self.assertEqual(len(projected["events"][0]["statements"]), 1)
        self.assertEqual(len(projected["events"][0]["disputed"]), 1)
        self.assertEqual(len(projected["events"][0]["unknown"]), 1)
        self.assertEqual(projected["events"][0]["analysis"], p["events"][0]["analysis"])

    def test_invalid_payloads_are_rejected_without_payload_echo(self):
        def change(path, value):
            def apply(p):
                node = p
                for key in path[:-1]:
                    node = node[key]
                node[path[-1]] = value

            return apply

        mutations = [
            change(["schema_version"], "unsupported"),
            change(["edition"], "2026-02-31"),
            change(["generated_at"], "2026-10-22T14:00:00"),
            change(["expires_at"], "2025-01-01T00:00:00Z"),
            change(["sources", 0, "allsides"], float("nan")),
            change(["sources", 0, "audience"], float("inf")),
            change(["sources", 0, "allsides"], True),
            change(["sources", 0, "audience"], 100),
            change(["events", 0, "topic_id"], "missing"),
            change(["events", 0, "date"], "2026-10-21"),
            change(
                ["events", 0, "analysis", "documents", 0, "url"], "javascript:alert(1)"
            ),
            change(
                ["events", 0, "analysis", "documents", 0, "url"], "https://127.0.0.1/"
            ),
            change(
                ["events", 0, "analysis", "documents", 0, "url"],
                "https://user:password@example.com/",
            ),
            change(["events", 0, "analysis", "documents", 0, "content_hash"], None),
            change(["events", 0, "analysis", "documents", 0, "access_level"], 3),
            change(
                ["events", 0, "analysis", "claims", 0, "supporting", 0, "document_id"],
                "missing",
            ),
            change(
                [
                    "events",
                    0,
                    "analysis",
                    "claims",
                    0,
                    "independent_verification",
                    "status",
                ],
                "contradicted",
            ),
            change(["events", 0, "analysis", "claims", 1, "attribution"], None),
            change(
                ["events", 0, "analysis", "claims", 0, "private_prompt"], "forbidden"
            ),
            change(["events", 0, "analysis", "claims", 0, "confidence_percentage"], 99),
            change(["events", 0, "analysis", "trace", 0, "evidence_refs"], ["missing"]),
            change(
                ["events", 0, "analysis", "coverage", "eligible_source_ids"],
                ["demo-office"],
            ),
            change(
                ["events", 0, "analysis", "coverage", "independent_confirmation_count"],
                5,
            ),
            change(["events", 0, "summary"], "Bearer " + "x" * 30),
        ]
        for i, mutation in enumerate(mutations):
            with self.subTest(case=i):
                p = sample()
                mutation(p)
                with self.assertRaises(SnapshotError) as raised:
                    validate_snapshot(p)
                self.assertLess(len(str(raised.exception)), 80)

    def test_json_size_duplicate_keys_depth_and_non_finite(self):
        for raw in (
            b" " * (MAX_BYTES + 1),
            b'{"a":1,"a":2}',
            b'{"a":NaN}',
            b"[" * 30 + b"0" + b"]" * 30,
            b"{}garbage",
        ):
            with self.subTest(size=len(raw)), self.assertRaises(SnapshotError):
                parse_snapshot(raw)

    def test_document_and_correction_times_cannot_postdate_generation(self):
        p = sample()
        p["events"][0]["analysis"]["documents"][0][
            "published_at"
        ] = "2026-10-23T14:00:00Z"
        with self.assertRaises(SnapshotError):
            validate_snapshot(p)

    def test_duplicate_ids_quote_offsets_and_revision_references(self):
        p = sample()
        p["events"].append(copy.deepcopy(p["events"][0]))
        with self.assertRaises(SnapshotError):
            validate_snapshot(p)
        p = sample()
        citation = p["events"][0]["analysis"]["claims"][0]["supporting"][0]
        citation.update(quote="demo", char_start=0, char_end=3)
        with self.assertRaises(SnapshotError):
            validate_snapshot(p)


@override_settings(DEBUG=True)
class StoreTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "snapshots"
        self.env = patch.dict(
            os.environ,
            {
                "QUORUM_SNAPSHOT_ROOT": str(self.root),
                "QUORUM_ENABLE_SNAPSHOT_PUBLICATION": "1",
                "QUORUM_CATALOG_PATH": "",
            },
        )
        self.env.start()
        self.clock = patch("portal.snapshot_store.now", return_value=CLOCK)
        self.clock.start()
        self.store = SnapshotStore()
        self.store.prepare()

    def tearDown(self):
        self.clock.stop()
        self.env.stop()
        self.temp.cleanup()

    def test_invalid_metadata_is_an_explicit_unavailable_revision(self):
        self.publish()
        meta = self.root / "revisions/demo-r1.meta.json"
        meta.write_text("[]")
        payload, status = self.store.read(revision="demo-r1")
        self.assertIsNone(payload)
        self.assertEqual(status["error_code"], "revision_unavailable")

    def publish(self, p=None):
        p = p or sample()
        raw = json.dumps(p, allow_nan=False).encode()
        path = self.root / "staging/input.json"
        path.write_bytes(raw)
        return self.store.publish(
            path, hashlib.sha256(raw).hexdigest(), allow_demo=True
        )

    def test_atomic_publication_selection_and_stale(self):
        self.publish()
        payload, meta = self.store.read("2026-10-22")
        self.assertEqual(payload["revision"], "demo-r1")
        self.assertEqual(meta["status"], "partial")
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(
            (self.root / "revisions/demo-r1.json").stat().st_mode & 0o777, 0o600
        )
        with patch(
            "portal.snapshot_store.now",
            return_value=datetime(2026, 10, 24, tzinfo=timezone.utc),
        ):
            self.assertEqual(self.store.read()[1]["status"], "stale")
        self.assertEqual(self.store.read("2026-10-21")[1]["status"], "pending")
        self.assertEqual(self.store.read(revision="../x")[1]["status"], "error")

    def test_immutable_revision_idempotence_and_rollback(self):
        one = self.publish()
        self.assertEqual(one, self.publish())
        p = sample()
        p["revision"] = "demo-r2"
        p["parent_revision"] = "demo-r1"
        p["events"][0]["summary"] = "DEMO corrected summary"
        p["events"][0]["analysis"]["corrections"] = [
            {
                "supersedes_claim_id": "demo-unknown",
                "replacement_claim_id": "demo-unknown",
                "previous_revision": "demo-r1",
                "timestamp": p["generated_at"],
                "summary": "DEMO correction",
            }
        ]
        self.publish(p)
        self.assertEqual(self.store.read()[0]["revision"], "demo-r2")
        self.assertEqual(self.store.read(revision="demo-r1")[0]["revision"], "demo-r1")
        p["events"][0]["summary"] = "different bytes under same revision"
        with self.assertRaises(SnapshotError):
            self.publish(p)
        self.store.rollback("demo-r1")
        self.assertEqual(self.store.read()[0]["revision"], "demo-r1")

    def test_failed_publication_preserves_last_known_good_and_audit(self):
        self.publish()
        p = sample()
        p["revision"] = "demo-r2"
        p["parent_revision"] = "demo-r1"
        p["events"][0]["topic_id"] = "missing"
        with self.assertRaises(SnapshotError):
            self.publish(p)
        self.assertEqual(self.store.read()[0]["revision"], "demo-r1")
        self.assertEqual(self.store.status()["validation_failures"], 1)
        self.assertEqual(
            self.store.status()["last_error"]["code"], "invalid_event_reference"
        )

    def test_integrity_failure_recovers_previous_head(self):
        self.publish()
        p = sample()
        p.update(revision="demo-r2", parent_revision="demo-r1")
        self.publish(p)
        (self.root / "revisions/demo-r2.json").write_text("{}")
        payload, meta = self.store.read()
        self.assertEqual(payload["revision"], "demo-r1")
        self.assertTrue(meta["fallback"])
        (self.root / "current.json").write_text("invalid")
        self.assertEqual(self.store.read()[0]["revision"], "demo-r1")
        (self.root / "revisions/demo-r1.json").write_text("{}")
        self.assertEqual(self.store.read()[1]["status"], "error")

    def test_staging_symlinks_gate_digest_and_production_demo_rejection(self):
        self.publish()
        link = self.root / "staging/link.json"
        link.symlink_to(self.root / "revisions/demo-r1.json")
        with self.assertRaises(SnapshotError):
            self.store.publish(link, "0" * 64, True)
        with self.assertRaises(SnapshotError):
            self.store.publish(self.root / "staging/input.json", "0" * 64, True)
        with patch.dict(
            os.environ, {"QUORUM_ENABLE_SNAPSHOT_PUBLICATION": "0"}
        ), self.assertRaises(SnapshotError):
            self.publish()
        with self.settings(DEBUG=False), self.assertRaises(SnapshotError):
            self.publish()
        with self.settings(DEBUG=False):
            self.assertEqual(self.store.read()[1]["status"], "error")

    def test_adapter_projection_and_stable_dateless_event_lookup(self):
        self.publish()
        adapter = PublishedAdapter()
        result = adapter.snapshot("2026-10-22", "demo-topic")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(adapter.snapshot("2026-10-22", "other")["events"], [])
        self.assertEqual(adapter.event("demo-event")["events"][0]["date"], "2026-10-22")
        self.assertEqual(adapter.event("missing")["events"], [])
        self.assertEqual(adapter.snapshot("2026-10-21")["events"], [])

    def test_atomic_commit_failure_keeps_old_head(self):
        self.publish()
        p = sample()
        p.update(revision="demo-r2", parent_revision="demo-r1")
        from .snapshot_store import atomic

        def fail_head(path, data):
            if path.name == "current.json":
                raise OSError("simulated full disk")
            return atomic(path, data)

        with patch(
            "portal.snapshot_store.atomic", side_effect=fail_head
        ), self.assertRaises(SnapshotError):
            self.publish(p)
        self.assertEqual(self.store.read()[0]["revision"], "demo-r1")

    def test_auth_database_paths_and_missing_configuration(self):
        from django.conf import settings

        with self.assertRaises(SnapshotError):
            SnapshotStore(settings.DATA_DIR).prepare()
        with patch.dict(os.environ, {"QUORUM_SNAPSHOT_ROOT": ""}):
            self.assertEqual(SnapshotStore().read()[1]["status"], "pending")
            self.assertIsNone(SnapshotStore().status()["validation_failures"])


class SnapshotAPITests(TestCase):
    def test_event_endpoint_auth_and_invalid_revision(self):
        self.assertEqual(self.client.get("/api/events/demo-event/").status_code, 401)
        user = User.objects.create_user(
            "snapshot-reader", password="only-a-local-test-password-928!"
        )
        self.client.force_login(user)
        self.assertEqual(self.client.get("/api/events/demo-event/").status_code, 200)
        self.assertEqual(
            self.client.get("/api/events/demo-event/?date=bad").status_code, 400
        )
        self.assertEqual(
            self.client.get("/api/events/demo-event/?revision=../x").status_code, 400
        )
        self.assertEqual(self.client.get("/api/feed/?revision=../x").status_code, 400)
        self.assertEqual(self.client.post("/api/events/demo-event/").status_code, 405)
        self.assertEqual(self.client.get("/staff/").status_code, 302)


@override_settings(DEBUG=True)
class PublishedAPITests(TestCase):
    def test_validated_snapshot_reaches_authenticated_feed_event_and_control(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ,
            {
                "QUORUM_SNAPSHOT_ROOT": str(Path(temp) / "snapshots"),
                "QUORUM_ENABLE_SNAPSHOT_PUBLICATION": "1",
            },
        ), patch("portal.snapshot_store.now", return_value=CLOCK):
            store = SnapshotStore()
            store.prepare()
            raw = FIXTURE.read_bytes()
            candidate = store.root / "staging/candidate.json"
            candidate.write_bytes(raw)
            store.publish(candidate, hashlib.sha256(raw).hexdigest(), allow_demo=True)
            user = User.objects.create_user("api-reader")
            self.client.force_login(user)
            response = self.client.get("/api/feed/?date=2026-10-22&topic=demo-topic")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "demo")
            self.assertEqual(response.json()["publication"]["revision"], "demo-r1")
            self.assertEqual(response["Cache-Control"], "no-store")
            response = self.client.get("/api/events/demo-event/?revision=demo-r1")
            self.assertEqual(
                response.json()["events"][0]["analysis"]["claims"][2]["status"],
                "disputed",
            )
            self.assertEqual(
                self.client.get("/api/events/demo-event/?date=20261022").status_code,
                400,
            )
            self.assertEqual(
                self.client.get("/api/feed/?date=20261022").status_code, 400
            )
            self.assertEqual(self.client.get("/staff/status/").status_code, 302)
            admin = User.objects.create_superuser("api-admin")
            self.client.force_login(admin)
            response = self.client.get("/staff/status/")
            self.assertContains(response, "demo-r1")
            self.assertContains(response, "DEMO")
            self.assertEqual(response.context["operational"]["event_count"], 1)
