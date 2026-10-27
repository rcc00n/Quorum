"""Validate reviewed photo metadata; --install is an explicit private presentation-only publication."""
import hashlib
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from portal.editorial_photos import MAX_BYTES, parse, publish, store, validate_bindings
from portal.snapshot_store import read_bounded
from portal.snapshot_validation import SnapshotError, require


class Command(BaseCommand):
    help = "Validate a curated lead-photo manifest against exact installed editions; no network or model calls."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--sha256", required=True)
        parser.add_argument("--install", action="store_true")
        parser.add_argument("--expected-current", help="Current manifest SHA256, or 'none' for first install.")

    def handle(self, *args, **options):
        try:
            raw = read_bounded(Path(options["file"]), MAX_BYTES)
            digest = hashlib.sha256(raw).hexdigest()
            require(digest == options["sha256"], "photo_manifest_hash_mismatch")
            p = parse(raw)
            validate_bindings(p)
            try:
                current = hashlib.sha256(read_bounded(store() / "current.json", MAX_BYTES)).hexdigest()
            except FileNotFoundError:
                current = "none"
            if options["install"]:
                publish(raw, options["expected_current"])
            self.stdout.write(json.dumps({"valid": True, "entries": len(p["entries"]), "sha256": digest,
                                          "previous_sha256": current, "installed": bool(options["install"])}))
        except (OSError, SnapshotError, TypeError, ValueError, KeyError) as e:
            code = str(e) if isinstance(e, SnapshotError) else "photo_manifest_unavailable"
            raise CommandError(code) from None
