from django.core.management.base import BaseCommand, CommandError
from portal.snapshot_store import SnapshotStore
from portal.snapshot_validation import SnapshotError


class Command(BaseCommand):
    help = "Local-only PROPOSAL snapshot publisher. Disabled unless explicitly authorized/configured."

    def add_arguments(self, parser):
        parser.add_argument(
            "action", choices=["prepare", "publish", "rollback", "status"]
        )
        parser.add_argument("--file")
        parser.add_argument("--sha256")
        parser.add_argument("--revision")
        parser.add_argument("--allow-demo", action="store_true")

    def handle(self, *args, **options):
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
