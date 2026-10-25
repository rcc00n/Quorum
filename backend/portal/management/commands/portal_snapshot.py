from django.core.management.base import BaseCommand, CommandError
from portal.snapshot_store import SnapshotStore, read_bounded
from portal.snapshot_validation import SnapshotError
from portal.snapshot_compatibility import compatibility_report


class Command(BaseCommand):
    help = "Local-only PROPOSAL snapshot publisher. Disabled unless explicitly authorized/configured."

    def add_arguments(self, parser):
        parser.add_argument(
            "action", choices=["validate", "prepare", "publish", "rollback", "status"]
        )
        parser.add_argument("--file")
        parser.add_argument("--sha256")
        parser.add_argument("--revision")
        parser.add_argument("--allow-demo", action="store_true")

    def handle(self, *args, **options):
        if options["action"] == "validate":
            import json
            from pathlib import Path

            try:
                if not options["file"]:
                    raise SnapshotError("candidate_file_required")
                report = compatibility_report(read_bounded(Path(options["file"])))
            except (OSError, SnapshotError) as exc:
                report = compatibility_report(error=exc)
            self.stdout.write(json.dumps(report, sort_keys=True))
            if not report["compatible"]:
                # stdout is the machine-readable report; stderr is value-free.
                raise CommandError("Snapshot compatibility failed", returncode=1)
            return
        store = SnapshotStore()
        try:
            if options["action"] == "prepare":
                import os

                if os.getenv("QUORUM_ENABLE_SNAPSHOT_PUBLICATION") != "1":
                    raise SnapshotError("publication_disabled")
                store.prepare()
                self.stdout.write(
                    "Private local staging prepared; no transport enabled"
                )
            elif options["action"] == "publish":
                if not options["file"]:
                    raise SnapshotError("staged_file_required")
                meta = store.publish(
                    options["file"], options["sha256"], options["allow_demo"]
                )
                self.stdout.write("Published validated revision " + meta["revision"])
            elif options["action"] == "rollback":
                meta = store.rollback(options["revision"])
                self.stdout.write("Selected intact revision " + meta["revision"])
            else:
                import json

                self.stdout.write(json.dumps(store.status()))
        except (SnapshotError, OSError, TypeError) as exc:
            raise CommandError(
                str(exc)
                if isinstance(exc, SnapshotError)
                else "snapshot_operation_failed"
            ) from None
