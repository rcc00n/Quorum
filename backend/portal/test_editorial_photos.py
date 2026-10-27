"""TEST photo metadata and private scratch files only; no network or provider call."""
import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from . import editorial_photos as photos
from .snapshot_validation import SnapshotError


def manifest():
    return {"schema": photos.SCHEMA, "reviewed_by": "TEST operator / Codex", "reviewed_at": "2026-10-27T19:00:00Z",
            "entries": [{"topic_id": "TEST-topic".lower(), "edition_date": "2026-10-27", "snapshot_sha256": "a" * 64,
                         "event_id": "TEST-event", "photo": {
                             "url": "https://upload.wikimedia.org/TEST-photo.jpg",
                             "source_url": "https://commons.wikimedia.org/wiki/File:TEST-photo.jpg",
                             "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                             "license": "CC0-1.0", "credit": "TEST photographer", "caption": "TEST file photo.",
                             "rights_confirmed": True}}]}


def encoded(p):
    return json.dumps(p).encode()


class EditorialPhotoTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = override_settings(DATA_DIR=Path(self.temp.name))
        self.config.enable()
        self.addCleanup(self.config.disable)

    def test_exact_schema_licence_origin_rights_and_json(self):
        p = manifest()
        self.assertEqual(photos.parse(encoded(p)), p)
        thumbnail = deepcopy(p); thumbnail['entries'][0]['photo']['url'] = 'https://thumb.wikimedia.org/TEST.jpg'
        self.assertEqual(photos.parse(encoded(thumbnail)), thumbnail)
        for key, value in (("rights_confirmed", False), ("rights_confirmed", 1), ("credit", ""),
                           ("license", "All rights reserved"), ("url", "http://upload.wikimedia.org/a.jpg"),
                           ("url", "https://upload.wikimedia.org.evil.example/a.jpg"),
                           ("url", "https://thumb.wikimedia.org.evil.example/a.jpg"),
                           ("source_url", "https://reuters.com/a"),
                           ("license_url", "https://evil.example/licence"),
                           ("url", "https://{}@upload.wikimedia.org/a.jpg".format("TEST-user:TEST-pass")),
                           ("url", "https://upload.wikimedia.org:443/a.jpg")):
            q = deepcopy(p); q["entries"][0]["photo"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(SnapshotError):
                photos.parse(encoded(q))
        for raw in (b'{"schema":1,"schema":2}', b'{"x":NaN}', b"[", b" " * (photos.MAX_BYTES + 1)):
            with self.subTest(raw_length=len(raw)), self.assertRaises(SnapshotError):
                photos.parse(raw)
        q = deepcopy(p); q["entries"].append(q["entries"][0])
        with self.assertRaises(SnapshotError): photos.parse(encoded(q))

    def test_exact_bytes_topic_day_and_event_binding_only_changes_presentation(self):
        p = manifest(); entry = p["entries"][0]
        photos.store().mkdir(); (photos.store() / "current.json").write_bytes(encoded(p))
        meta = {k: entry[k] for k in ("topic_id", "edition_date", "snapshot_sha256")}
        def events():
            return [{"id": "TEST-event", "article": {"photo": None}, "reasoning": {"photo": None}},
                    {"id": "TEST-other", "article": {"photo": None}}]
        for key in meta:
            rows = events(); bad = {**meta, key: "different"}
            photos.attach(rows, bad)
            self.assertIsNone(rows[0]["article"]["photo"])
        rows = events(); photos.attach(rows, meta)
        self.assertEqual(rows[0]["article"]["photo"], entry["photo"])
        self.assertIsNone(rows[0]["reasoning"]["photo"])
        self.assertIsNone(rows[1]["article"]["photo"])

    def test_missing_invalid_or_linked_manifest_keeps_news_readable(self):
        rows = [{"id": "TEST-event", "article": {"photo": None}}]
        original = deepcopy(rows)
        photos.attach(rows, {})
        self.assertEqual(rows, original)
        photos.store().mkdir(); target = photos.store() / "current.json"
        target.write_bytes(b"invalid")
        with self.assertLogs(photos.log, "WARNING"): photos.attach(rows, {})
        self.assertEqual(rows, original)
        target.unlink(); external = Path(self.temp.name) / "external.json"; external.write_bytes(encoded(manifest()))
        target.symlink_to(external)
        with self.assertLogs(photos.log, "WARNING"): photos.attach(rows, {})
        self.assertEqual(rows, original)

    @patch("portal.editorial_photos.validate_bindings")
    def test_atomic_publication_archive_stale_writer_and_rollback(self, binding):
        first = encoded(manifest()); digest = hashlib.sha256(first).hexdigest()
        self.assertEqual(photos.publish(first, "none"), digest)
        root = photos.store()
        self.assertEqual((root / "current.json").read_bytes(), first)
        self.assertEqual((root / f"{digest}.json").read_bytes(), first)
        self.assertEqual(os.stat(root / "current.json").st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)
        second = manifest(); second["entries"][0]["photo"]["caption"] = "TEST second reviewed caption."
        raw = encoded(second)
        with self.assertRaisesRegex(SnapshotError, "photo_manifest_changed"):
            photos.publish(raw, "none")
        self.assertEqual((root / "current.json").read_bytes(), first)
        newer = photos.publish(raw, digest)
        photos.publish(first, newer)
        self.assertEqual((root / "current.json").read_bytes(), first)
        self.assertEqual((root / f"{newer}.json").read_bytes(), raw)
