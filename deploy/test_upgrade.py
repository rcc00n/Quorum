"""Pure temporary-filesystem upgrade safety checks; no system services touched."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sqlite3

spec = importlib.util.spec_from_file_location(
    "upgrade", Path(__file__).with_name("upgrade-release.py")
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class UpgradeSafetyTests(unittest.TestCase):
    def test_target_tests_are_isolated_from_auth_and_installed_editions(self):
        original = {'DJANGO_SECRET_KEY': 'TEST-production-secret', 'QUORUM_PORTAL_DATA': '/var/lib/quorum',
                    'QUORUM_ENABLE_REASONING_READER': '1', 'QUORUM_REASONING_EDITIONS_ROOT': '/var/lib/quorum/editions',
                    'QUORUM_ENABLE_REASONING_PREVIEW': '1', 'QUORUM_SNAPSHOT_ROOT': '/TEST/published'}
        isolated = upgrade.isolated_test_environment(original, '/tmp/TEST-quorum-release')
        self.assertEqual(isolated['QUORUM_PORTAL_DATA'], '/tmp/TEST-quorum-release')
        self.assertNotEqual(isolated['DJANGO_SECRET_KEY'], original['DJANGO_SECRET_KEY'])
        self.assertEqual(isolated['QUORUM_ENABLE_REASONING_READER'], '0')
        self.assertEqual(isolated['QUORUM_REASONING_EDITIONS_ROOT'], '')
        self.assertEqual(isolated['QUORUM_SNAPSHOT_ROOT'], '')
        self.assertEqual(original['QUORUM_ENABLE_REASONING_READER'], '1')
        with self.assertRaisesRegex(RuntimeError, 'outside_production'):
            upgrade.isolated_test_environment(original, '/var/lib/quorum/TEST-tmp')

    def test_release_scope_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            release = root / "releases/review"
            for name in (
                "REVISION",
                "web/server.js",
                "backend/manage.py",
                "backend/requirements.txt",
            ):
                f = release / name
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("a" * 40 if name == "REVISION" else "")
            self.assertEqual(upgrade.release_path(release, root), release)
            link = root / "releases/link"
            link.symlink_to(release)
            with self.assertRaises(RuntimeError):
                upgrade.release_path(link, root)
            with self.assertRaises(RuntimeError):
                upgrade.release_path(root, root)

    def test_old_pins_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            old, new = Path(temp) / "old", Path(temp) / "new"
            old.write_text("Django==5.2.18\n")
            new.write_text("Django==5.2.18\njsonschema==4.26.0\n")
            self.assertEqual(
                upgrade.additive_requirements(old, new), {"jsonschema": "4.26.0"}
            )
            new.write_text("Django==5.3\n")
            with self.assertRaises(RuntimeError):
                upgrade.additive_requirements(old, new)

    def test_backup_integrity_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            source, backup = Path(temp) / "auth.sqlite3", Path(temp) / "backup.sqlite3"
            with sqlite3.connect(source) as db:
                db.execute("create table test(value text)")
                db.execute("insert into test values ('TEST-only')")
            upgrade.backup_database(source, backup)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            with sqlite3.connect(backup) as db:
                self.assertEqual(
                    db.execute("select value from test").fetchone()[0], "TEST-only"
                )
            with self.assertRaises(RuntimeError):
                upgrade.backup_database(source, backup)

    def test_atomic_switch_is_quorum_only(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            upgrade, "ROOT", Path(temp)
        ):
            root = Path(temp)
            (root / "current").symlink_to(root / "old")
            upgrade.switch(root / "new")
            self.assertEqual((root / "current").readlink(), root / "new")

    def test_enabled_publication_and_world_readable_environment_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            env = Path(temp) / "portal.env"
            env.write_text(
                "DJANGO_DEBUG=0\nDJANGO_SECRET_KEY=TEST\nQUORUM_PORTAL_DATA=/var/lib/quorum\nQUORUM_STATIC_ROOT=/opt/quorum/static\n"
            )
            env.chmod(0o600)
            upgrade.read_environment(env)
            env.write_text(env.read_text() + "QUORUM_ENABLE_SNAPSHOT_PUBLICATION=1\n")
            with self.assertRaises(RuntimeError):
                upgrade.read_environment(env)
            env.chmod(0o644)
            with self.assertRaises(RuntimeError):
                upgrade.read_environment(env)

    def test_failed_health_restores_previous_release_without_restoring_auth(self):
        import os

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "quorum"
            data = Path(temp) / "data"
            data.mkdir()
            (root / "static").mkdir(parents=True)
            (root / "static/test.css").write_text("TEST-only")
            for label in ("old", "new"):
                release = root / "releases" / label
                for name in (
                    "REVISION",
                    "web/server.js",
                    "backend/manage.py",
                    "backend/requirements.txt",
                ):
                    f = release / name
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("a" * 40 if name == "REVISION" else "")
            (root / "current").symlink_to(root / "releases/old")
            with sqlite3.connect(data / "portal.sqlite3") as db:
                for table in (
                    "auth_user",
                    "auth_user_groups",
                    "auth_user_user_permissions",
                    "portal_preference",
                ):
                    db.execute("CREATE TABLE " + table + " (id integer)")
                    db.execute("INSERT INTO " + table + " VALUES (1)")
            before = (data / "portal.sqlite3").read_bytes()
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                if args[:2] == ["systemctl", "is-active"]:
                    return "active\nactive\n"
                if args[0] == "ss":
                    return "LISTEN 127.0.0.1:3017\nLISTEN 127.0.0.1:8017\n"
                if "-c" in args:
                    return "{}"
                return ""

            real_release_path = upgrade.release_path
            with patch.object(upgrade.os, "chown"), patch.object(
                upgrade, "ROOT", root
            ), patch.object(upgrade, "DATA", data), patch.object(
                upgrade.os, "geteuid", return_value=0
            ), patch.object(
                upgrade, "read_environment", return_value={}
            ), patch.object(
                upgrade, "run", side_effect=fake_run
            ), patch.object(
                upgrade, "workloads", return_value=[]
            ), patch.object(
                upgrade,
                "release_path",
                side_effect=lambda p: real_release_path(p, root),
            ), patch.object(
                upgrade,
                "health",
                side_effect=[RuntimeError("TEST health failure"), None],
            ), patch.object(
                upgrade.pwd,
                "getpwnam",
                return_value=type(
                    "Account", (), {"pw_uid": os.getuid(), "pw_gid": os.getgid()}
                )(),
            ):
                with self.assertRaisesRegex(RuntimeError, "TEST health failure"):
                    upgrade.execute(root / "releases/new", apply=True)
            self.assertEqual((root / "current").resolve(), root / "releases/old")
            self.assertEqual(before, (data / "portal.sqlite3").read_bytes())
            service_commands = [c for c in commands if c[0] == "systemctl"]
            self.assertTrue(
                all(c[2:] == ["quorum-api", "quorum-web"] for c in service_commands)
            )
