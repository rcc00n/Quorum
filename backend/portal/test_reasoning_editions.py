"""Login-only reader tests: synthetic editions in a temporary directory, stubbed Git reads, no provider calls."""
import hashlib
import io
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from .reasoning_preview import SAMPLE
from .reasoning_editions import ENABLE, ROOT

CONFIG = b"TEST config"
COMMAND = "portal.management.commands.reasoning_snapshot.subprocess.check_output"


def genuine(name, topic_id=None):
    """A bundled fictional sample relabelled as a TEST genuine run (never a real provider output)."""
    p = json.loads(SAMPLE.with_name(name).read_bytes())
    p["provenance"].update(fictional=False, corpus="zetaris", model="TEST/model", model_calls=1,
                           model_errors=0, answered_by={"TEST/model": 1})
    if topic_id:
        p["topic_id"] = topic_id
        p["run_id"] = f"{p['edition_date']}-{topic_id}-{p['version']}"
    return p


class ReasoningEditionsTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "editions"
        self.root.mkdir(mode=0o700)
        self.work = Path(self.temp.name) / "work"
        self.work.mkdir()
        self.reader = User.objects.create_user("TEST-editions-reader")
        self.env = patch.dict(os.environ, {ENABLE: "1", ROOT: str(self.root), "QUORUM_CATALOG_PATH": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.clock = patch('portal.reasoning_editions._now', return_value=datetime(2026, 10, 22, 12, tzinfo=timezone.utc))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def write(self, p, label, provisional=False):
        raw = json.dumps(p).encode()
        sidecar = dict(
            snapshot={k: p[k] for k in ("topic_id", "edition_date", "version", "run_id", "status")},
            provisional=provisional, corpus_as_of_utc=p["window"]["start"],
            edition_window_utc=[p["window"][k] for k in ("start", "end")],
            producer=dict(commit="aaaaaaa (TEST producer)", config_sha256=hashlib.sha256(CONFIG).hexdigest()),
            private_evidence=dict(log="TEST-private-path"),
        )
        sidecar["snapshot"]["sha256"] = hashlib.sha256(raw).hexdigest()
        sidecar_raw = json.dumps(sidecar).encode()
        (self.work / f"{label}.json").write_bytes(raw)
        (self.work / f"{label}.sidecar.json").write_bytes(sidecar_raw)
        return dict(file=str(self.work / f"{label}.json"), sha256=hashlib.sha256(raw).hexdigest(),
                    sidecar=str(self.work / f"{label}.sidecar.json"),
                    sidecar_sha256=hashlib.sha256(sidecar_raw).hexdigest(), producer_commit="a" * 40)

    def accept(self, options, blocked=False, **changes):
        out = io.StringIO()
        with patch(COMMAND, return_value=CONFIG):
            if blocked:
                with self.assertRaises(CommandError):
                    call_command("reasoning_snapshot", stdout=out, **(options | changes))
            else:
                call_command("reasoning_snapshot", stdout=out, **(options | changes))
        self.assertNotIn("TEST-private-path", out.getvalue())
        return json.loads(out.getvalue())

    def install_two_topics(self):
        story = genuine("snapshot.sample.json")
        quiet = genuine("snapshot.empty-day.sample.json", "climate-policy")
        self.accept(self.write(story, "story"), install=True)
        self.accept(self.write(quiet, "quiet"), install=True)
        return story, quiet

    def test_reader_off_or_unconfigured_changes_nothing(self):
        self.install_two_topics()
        self.client.force_login(self.reader)
        for env in ({ENABLE: "0"}, {ROOT: ""}, {ROOT: "relative/editions"}):
            with self.subTest(env=env), patch.dict(os.environ, env):
                data = self.client.get("/api/feed/?date=2026-10-22").json()
                self.assertEqual(data["status"], "pending")
                self.assertEqual(data["events"], [])
                self.assertEqual(data["publication"]["status"], "pending")

    def test_reviewed_photo_reaches_authenticated_reader_without_changing_original(self):
        from .test_editorial_photos import manifest
        p, quiet = self.install_two_topics()
        installed = self.root / p['topic_id'] / p['edition_date'] / 'v1.json'
        raw = installed.read_bytes()
        before = {str(f): f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        m = manifest(); entry = m['entries'][0]
        entry.update(topic_id=p['topic_id'], edition_date=p['edition_date'],
                     snapshot_sha256=hashlib.sha256(raw).hexdigest(), event_id=p['stories'][0]['event_id'])
        source = self.work / 'photos.json'; source.write_text(json.dumps(m))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with override_settings(DATA_DIR=self.work):
            out = io.StringIO()
            call_command('editorial_photos', file=str(source), sha256=digest, install=True,
                         expected_current='none', stdout=out)
            self.assertTrue(json.loads(out.getvalue())['installed'])
            self.assertEqual(self.client.get('/api/feed/?date=2026-10-22').status_code, 401)
            self.client.force_login(self.reader)
            data = self.client.get('/api/feed/?date=2026-10-22').json()
            row = next(e for e in data['events'] if e['id'] == entry['event_id'])
            self.assertEqual(row['article']['photo'], entry['photo'])
            self.assertEqual(row['reasoning']['photo'], p['stories'][0]['photo'])
            # A newer/different original can never inherit this photo based on its title alone.
            m['entries'][0]['snapshot_sha256'] = 'b' * 64
            source.write_text(json.dumps(m))
            with self.assertRaises(CommandError):
                call_command('editorial_photos', file=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual({str(f): f.read_bytes() for f in self.root.rglob('*') if f.is_file()}, before)

    def test_installed_editions_reach_only_signed_in_readers(self):
        story, quiet = self.install_two_topics()
        self.assertEqual(self.client.get("/api/feed/?date=2026-10-22").status_code, 401)
        self.client.force_login(self.reader)
        data = self.client.get("/api/feed/?date=2026-10-22").json()
        self.assertEqual(data["status"], "available")
        self.assertEqual(data["publication"]["status"], "available")
        self.assertEqual(data["publication"]["revision"], "editions-2026-10-22")
        self.assertEqual(data["publication"]["mode"], "live")
        self.assertFalse(data["publication"]["fallback"])
        self.assertTrue(data["publication"]["published_at"].endswith("Z"))
        self.assertEqual({t["id"] for t in data["topics"]}, {"russia-ukraine-war", "climate-policy"})
        self.assertEqual([e["topic_id"] for e in data["events"]], ["russia-ukraine-war"] * len(story["stories"]))
        for event in data["events"]:
            # The presentation is the preview's: the story's reasoning block, never an invented analysis.
            self.assertIn("reasoning", event)
            self.assertNotIn("analysis", event)
        editions = {e["topic_id"]: e for e in data["editions"]}
        self.assertEqual(set(editions), {"russia-ukraine-war", "climate-policy"})
        self.assertTrue(editions["climate-policy"]["quiet_day"])
        self.assertEqual(editions["climate-policy"]["completion"], "complete")
        self.assertEqual(editions["climate-policy"]["summary"], quiet["summary"])
        items = [i for g in editions["climate-policy"]["roundup"] for i in g["items"]]
        self.assertEqual(len(items), quiet["roundup"]["count"])
        self.assertTrue(all(i["event_id"] is None and i["status"] == "unknown" for i in items))
        self.assertEqual(data["errors"], [])
        self.assertNotIn("TEST-private-path", json.dumps(data))
        by_topic = self.client.get("/api/feed/?date=2026-10-22&topic=climate-policy").json()
        self.assertEqual(by_topic["events"], [])
        self.assertEqual([e["topic_id"] for e in by_topic["editions"]], ["climate-policy"])
        other = self.client.get("/api/feed/?date=2026-10-22&revision=other").json()
        self.assertEqual(other["publication"]["status"], "pending")
        missing_day = self.client.get("/api/feed/?date=2026-10-23").json()
        self.assertEqual(missing_day["publication"]["status"], "pending")
        missing_topic = self.client.get("/api/feed/?date=2026-10-22&topic=ai-regulation").json()
        self.assertEqual(missing_topic["publication"]["status"], "pending")

    def test_event_detail_comes_from_the_installed_edition(self):
        story, _ = self.install_two_topics()
        event_id = story["stories"][0]["event_id"]
        self.client.force_login(self.reader)
        for query in ("?date=2026-10-22", ""):
            with self.subTest(query=query):
                data = self.client.get(f"/api/events/{event_id}/{query}").json()
                self.assertEqual([e["id"] for e in data["events"]], [event_id])
                self.assertEqual(data["events"][0]["reasoning"]["reading_minutes"], story["stories"][0]["reading_minutes"])
                self.assertEqual(data["publication"]["revision"], "editions-2026-10-22")
                context = data['events'][0]['reasoning_context']
                self.assertEqual(context['trace'], story['trace'])
                self.assertEqual(context['roundup'], story['roundup'])
                self.assertEqual(context['stories'], [{k: s[k] for k in ('event_id', 'headline')} for s in story['stories']])
        unknown = self.client.get("/api/events/TEST-unknown/?date=2026-10-22").json()
        self.assertEqual(unknown["events"], [])
        self.assertEqual(unknown["publication"]["revision"], "editions-2026-10-22")
        nowhere = self.client.get("/api/events/TEST-unknown/").json()
        self.assertEqual(nowhere["events"], [])
        self.assertEqual(nowhere["publication"]["status"], "pending")

    def test_expired_installed_editions_keep_content_under_a_stale_notice(self):
        story, _ = self.install_two_topics()
        expiry = datetime.fromisoformat(story['expires_at'].replace('Z', '+00:00'))
        self.client.force_login(self.reader)
        with patch('portal.reasoning_editions._now', return_value=expiry + timedelta(seconds=1)):
            feed = self.client.get('/api/feed/?date=2026-10-22').json()
            self.assertEqual(feed['publication']['status'], 'stale')
            self.assertEqual(len(feed['events']), len(story['stories']))
            detail = self.client.get(f"/api/events/{story['stories'][0]['event_id']}/?date=2026-10-22").json()
            self.assertEqual(detail['publication']['status'], 'stale')
            self.assertEqual(detail['events'][0]['reasoning'], story['stories'][0])

    def test_fictional_installs_only_in_debug_and_reads_as_demo(self):
        sample = json.loads(SAMPLE.read_bytes())
        options = self.write(sample, "fictional")
        report = self.accept(options, blocked=True, install=True)
        self.assertIn("genuine_model_output_required", report["issues"])
        with override_settings(DEBUG=False):
            report = self.accept(options, blocked=True, install=True, allow_fictional=True)
        self.assertIn("allow_fictional_requires_debug", report["issues"])
        with override_settings(DEBUG=True):
            report = self.accept(options, install=True, allow_fictional=True)
        self.assertTrue(report["installed"] and report["fictional"])
        self.assertFalse(report["published"])
        self.assertTrue((self.root / "russia-ukraine-war/2026-10-22/v1.json").is_file())
        self.assertEqual((self.root / "russia-ukraine-war/2026-10-22/v1.json").stat().st_mode & 0o777, 0o600)
        self.client.force_login(self.reader)
        with override_settings(DEBUG=True):
            data = self.client.get("/api/feed/?date=2026-10-22").json()
        self.assertEqual(data["status"], "demo")
        self.assertEqual(data["publication"]["mode"], "demo")
        self.assertEqual(len(data["events"]), len(sample["stories"]))
        with override_settings(DEBUG=False):
            data = self.client.get("/api/feed/?date=2026-10-22").json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data['events'], [])

    def test_missing_or_changed_install_triplet_fails_closed(self):
        story = genuine('snapshot.sample.json')
        self.accept(self.write(story, 'integrity'), install=True)
        folder = self.root / story['topic_id'] / story['edition_date']
        self.client.force_login(self.reader)
        for filename in ('v1.sidecar.json', 'v1.meta.json', 'v1.json'):
            path = folder / filename
            original = path.read_bytes()
            changed_bytes = (json.dumps({**json.loads(original), 'snapshot_sha256': '0' * 64}).encode()
                             if filename == 'v1.meta.json' else original + b' ')
            for changed in (None, changed_bytes):
                with self.subTest(filename=filename, missing=changed is None):
                    if changed is None:
                        path.unlink()
                    else:
                        path.write_bytes(changed)
                    # A missing snapshot is a genuinely absent install; other broken triplet members are errors.
                    data = self.client.get('/api/feed/?date=2026-10-22').json()
                    self.assertEqual(data['events'], [])
                    if filename != 'v1.json' or changed is not None:
                        self.assertEqual(data['status'], 'error')
                        self.assertEqual(data['publication']['status'], 'error')
                    path.write_bytes(original)

    def test_versions_are_immutable_and_a_broken_file_becomes_an_error_row(self):
        story, _ = self.install_two_topics()
        report = self.accept(self.write(story, "again"), blocked=True, install=True)
        self.assertIn("edition_version_already_installed", report["issues"])
        (self.root / "russia-ukraine-war/2026-10-22/v2.json").write_text("{not json")
        self.client.force_login(self.reader)
        data = self.client.get("/api/feed/?date=2026-10-22").json()
        self.assertEqual([e["code"] for e in data["errors"]], ["reasoning_edition_invalid"])
        self.assertEqual([e["topic_id"] for e in data["errors"]], ["russia-ukraine-war"])
        self.assertEqual(set(data["errors"][0]), {"code", "message", "event_id", "topic_id"})
        self.assertEqual(data["events"], [])
        self.assertEqual([e["topic_id"] for e in data["editions"]], ["climate-policy"])
        self.assertEqual(data["publication"]["status"], "available")

    def test_install_needs_a_configured_root_and_a_clean_acceptance(self):
        story = genuine("snapshot.sample.json")
        options = self.write(story, "story")
        with patch.dict(os.environ, {ROOT: ""}):
            report = self.accept(options, blocked=True, install=True)
        self.assertIn("editions_root_not_configured", report["issues"])
        self.assertEqual(list(self.root.iterdir()), [])
        report = self.accept(options, blocked=True, install=True, producer_commit="b" * 40)
        self.assertIn("producer_commit_mismatch", report["issues"])
        self.assertEqual(list(self.root.iterdir()), [])
        report = self.accept(options)
        self.assertNotIn("installed", report)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_install_enforces_private_directories_and_refuses_links(self):
        story = genuine('snapshot.sample.json')
        options = self.write(story, 'permissions')
        topic = self.root / story['topic_id']
        topic.mkdir(mode=0o755)
        self.accept(options, install=True)
        day = topic / story['edition_date']
        for path in (self.root, topic, day):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for path in day.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        other = genuine('snapshot.sample.json', 'linked-topic')
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (self.root / 'linked-topic').symlink_to(outside, target_is_directory=True)
        report = self.accept(self.write(other, 'linked'), blocked=True, install=True)
        self.assertIn('linked_editions_directory', report['issues'])
        self.assertEqual(list(outside.iterdir()), [])

    def test_honesty_labels_travel_with_the_edition(self):
        story = genuine("snapshot.sample.json")
        self.accept(self.write(story, "story", provisional=True), install=True)
        self.client.force_login(self.reader)
        data = self.client.get("/api/feed/?date=2026-10-22").json()
        edition = data["editions"][0]
        self.assertTrue(edition["provisional"])
        self.assertEqual(edition["corpus_as_of_utc"], story["window"]["start"])
        self.assertEqual(edition["edition_window_utc"], [story["window"]["start"], story["window"]["end"]])
        self.assertFalse(edition["closed_edition"])
        self.assertTrue(any("not publication-approved" in w for w in edition["warnings"]))
        self.assertTrue(data["publication"]["provisional"])
        self.assertEqual(data["publication"]["corpus_as_of_utc"], edition["corpus_as_of_utc"])
        self.assertEqual(data["publication"]["warnings"], edition["warnings"])
        self.assertIn("missing_provenance", edition)
        self.assertNotIn("_edition_of_event", data)
        detail = self.client.get(f"/api/events/{story['stories'][0]['event_id']}/?date=2026-10-22").json()
        self.assertEqual(detail["publication"]["corpus_as_of_utc"], edition["corpus_as_of_utc"])
        self.assertNotIn("_edition_of_event", detail)
        self.assertEqual(data["publication"]["installed_at"], data["publication"]["published_at"])

    def test_roundup_vocabulary_maps_to_claim_statuses_and_keeps_the_labels(self):
        quiet = genuine("snapshot.empty-day.sample.json", "climate-policy")
        items = [i for g in quiet["roundup"]["groups"] for i in g["items"]]
        labels = ["statements only", "single source", "reported, not confirmed"][: len(items)]
        for item, label in zip(items, labels):
            item["status"] = label
            item["line_source"] = "title"
            item["needs_review"] = True
        self.accept(self.write(quiet, "quiet"), install=True)
        self.client.force_login(self.reader)
        data = self.client.get("/api/feed/?date=2026-10-22&topic=climate-policy").json()
        rows = [i for g in data["editions"][0]["roundup"] for i in g["items"]]
        self.assertEqual([r["label"] for r in rows], labels)
        expected = {"statements only": "attributed", "single source": "unknown", "reported, not confirmed": "unknown"}
        self.assertEqual([r["status"] for r in rows], [expected[l] for l in labels])
        self.assertTrue(all(r["line_source"] == "title" and r["needs_review"] is True for r in rows))

    def test_recorded_failures_carry_code_and_topic_and_leave_other_quiet_days(self):
        # A partial edition of one topic and a quiet edition of another on the same day: the failures reach the API
        # in its own shape with their topic, and the quiet topic stays complete and quiet (2026-10-27).
        partial = genuine("snapshot.partial.sample.json")
        quiet = genuine("snapshot.empty-day.sample.json", "climate-policy")
        self.assertTrue(partial["errors"])
        self.accept(self.write(partial, "partial"), install=True)
        self.accept(self.write(quiet, "quiet"), install=True)
        self.client.force_login(self.reader)
        data = self.client.get("/api/feed/?date=2026-10-22").json()
        self.assertEqual(len(data["errors"]), len(partial["errors"]))
        for row in data["errors"]:
            self.assertEqual(set(row), {"code", "message", "event_id", "topic_id"})
            self.assertTrue(row["code"].startswith("reasoning_"))
            self.assertEqual(row["topic_id"], "russia-ukraine-war")
            self.assertNotIn("node", row)
        self.assertEqual({r["code"] for r in data["errors"]}, {"reasoning_" + e["node"] for e in partial["errors"]})
        editions = {e["topic_id"]: e for e in data["editions"]}
        self.assertEqual(editions["russia-ukraine-war"]["completion"], "partial")
        self.assertEqual(editions["climate-policy"]["completion"], "complete")
        self.assertTrue(editions["climate-policy"]["quiet_day"])
        self.assertEqual(data["publication"]["status"], "available")

    def test_a_legacy_string_failure_is_coded_and_never_breaks_the_day(self):
        # The parser still accepts plain-string errors from older producers; the feed and the event route keep
        # answering, with the row coded and scoped to its topic (review of 2026-10-27).
        partial = genuine("snapshot.sample.json")
        partial["status"] = "partial"
        partial["errors"] = ["model route returned HTTP 502", "TEST-secret token=abc at /srv/TEST-private.log"]
        quiet = genuine("snapshot.empty-day.sample.json", "climate-policy")
        self.accept(self.write(partial, "legacy"), install=True)
        self.accept(self.write(quiet, "quiet"), install=True)
        self.client.force_login(self.reader)
        response = self.client.get("/api/feed/?date=2026-10-22")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # The allow-listed transport line passes through; anything else is the preview's withheld sentence.
        self.assertEqual(data["errors"], [
            {"code": "reasoning_error", "message": "model route returned HTTP 502", "event_id": None, "topic_id": "russia-ukraine-war"},
            {"code": "reasoning_error", "message": "Recorded upstream failure; internal details withheld.", "event_id": None,
             "topic_id": "russia-ukraine-war"},
        ])
        self.assertNotIn("TEST-secret", response.content.decode())
        self.assertNotIn("TEST-private", response.content.decode())
        editions = {e["topic_id"]: e for e in data["editions"]}
        self.assertEqual(editions["russia-ukraine-war"]["completion"], "partial")
        self.assertTrue(editions["climate-policy"]["quiet_day"])
        event_id = partial["stories"][0]["event_id"]
        for url in (f"/api/events/{event_id}/?date=2026-10-22", f"/api/events/{event_id}/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_a_declared_missing_source_makes_the_edition_partial(self):
        p = genuine("snapshot.sample.json")
        p["sources_missing"] = ["TEST-source"]
        self.accept(self.write(p, "missing"), install=True)
        self.client.force_login(self.reader)
        data = self.client.get("/api/feed/?date=2026-10-22").json()
        self.assertEqual(data["editions"][0]["completion"], "partial")
        self.assertEqual(data["publication"]["status"], "partial")

    def test_producer_config_file_replaces_the_git_lookup(self):
        story = genuine("snapshot.sample.json")
        options = self.write(story, "story")
        config = self.work / "reasoning.toml"
        config.write_bytes(CONFIG)
        out = io.StringIO()
        with patch(COMMAND, side_effect=AssertionError("git must not be called")):
            call_command("reasoning_snapshot", stdout=out, **options, producer_config=str(config), install=True)
        report = json.loads(out.getvalue())
        self.assertTrue(report["metadata_valid"] and report["installed"])
        self.assertEqual(report["config_source"], "file")
        config.write_bytes(b"TEST other config")
        out = io.StringIO()
        with patch(COMMAND, side_effect=AssertionError("git must not be called")), self.assertRaises(CommandError):
            call_command("reasoning_snapshot", stdout=out, **options, producer_config=str(config))
        self.assertIn("producer_config_mismatch", json.loads(out.getvalue())["issues"])
