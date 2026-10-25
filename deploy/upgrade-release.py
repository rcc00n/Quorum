#!/usr/bin/env python3
"""Existing Quorum deployment only. No migrations, global config edits or processing."""

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

ROOT = Path("/opt/quorum")
ENV = Path("/etc/quorum/portal.env")
DATA = Path("/var/lib/quorum")
UNITS = ["quorum-api", "quorum-web"]


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    require(result.returncode == 0, "command_failed:" + Path(str(args[0])).name)
    return result.stdout


def release_path(path, root=ROOT):
    p = Path(path)
    require(
        p.is_absolute() and not p.is_symlink() and p.resolve() == p,
        "unsafe_release_path",
    )
    require(
        p.parent == root / "releases" and re.fullmatch(r"[A-Za-z0-9_-]+", p.name),
        "release_outside_quorum",
    )
    require(
        all(
            (p / item).is_file()
            for item in (
                "REVISION",
                "web/server.js",
                "backend/manage.py",
                "backend/requirements.txt",
            )
        ),
        "incomplete_release",
    )
    require(
        re.fullmatch(r"[a-f0-9]{40}\n?", (p / "REVISION").read_text()),
        "invalid_release_revision",
    )
    return p


def pins(path):
    result = {}
    for line in path.read_text().splitlines():
        require(
            re.fullmatch(r"[A-Za-z0-9_-]+==[0-9A-Za-z.+-]+", line) is not None,
            "unpinned_requirement",
        )
        name, version = line.split("==")
        result[name.lower().replace("_", "-")] = version
    return result


def additive_requirements(previous, candidate):
    old, new = pins(previous), pins(candidate)
    require(all(new.get(k) == v for k, v in old.items()), "existing_dependency_changed")
    return {k: v for k, v in new.items() if k not in old}


def read_environment(path):
    require(
        path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0,
        "unsafe_private_environment",
    )
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = shlex.split(line)
        require(len(parts) == 1 and "=" in parts[0], "unsupported_environment_syntax")
        key, value = parts[0].split("=", 1)
        values[key] = value
    require(
        values.get("DJANGO_DEBUG") == "0" and bool(values.get("DJANGO_SECRET_KEY")),
        "production_settings_required",
    )
    require(values.get("QUORUM_PORTAL_DATA") == str(DATA), "wrong_auth_database")
    require(
        values.get("QUORUM_STATIC_ROOT") == str(ROOT / "static"),
        "wrong_static_directory",
    )
    require(
        values.get("QUORUM_ENABLE_SNAPSHOT_PUBLICATION") != "1"
        and not values.get("QUORUM_SNAPSHOT_ROOT"),
        "publication_must_remain_disabled",
    )
    return values


def fingerprint(db):
    con = sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True)
    try:
        values = {
            table: con.execute("SELECT * FROM " + table + " ORDER BY 1").fetchall()
            for table in (
                "auth_user",
                "auth_user_groups",
                "auth_user_user_permissions",
                "portal_preference",
            )
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    finally:
        con.close()


def backup_database(source, destination):
    require(not destination.exists(), "backup_already_exists")
    with sqlite3.connect(
        "file:" + str(source) + "?mode=ro", uri=True
    ) as src, sqlite3.connect(destination) as dest:
        src.backup(dest)
        require(
            dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
            "backup_integrity_failed",
        )
    destination.chmod(0o600)


def switch(release):
    link = ROOT / "current.next"
    require(
        not link.exists() and not link.is_symlink(), "unexpected_release_switch_file"
    )
    link.symlink_to(release)
    os.replace(link, ROOT / "current")


def health():
    for endpoint, expected in [
        ("/", 200),
        ("/login", 200),
        ("/register", 200),
        ("/api/session/", 200),
        ("/api/feed/", 401),
        ("/staff/login/", 200),
    ]:
        passed = False
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    "https://quorum.raccncode.com" + endpoint, timeout=10
                ) as response:
                    code = response.status
            except urllib.error.HTTPError as error:
                code = error.code
            except (OSError, urllib.error.URLError):
                code = None
            if code == expected:
                passed = True
                break
            if attempt < 2:
                time.sleep(2)
        require(passed, "https_health_failed")


def workloads():
    ids = run(["docker", "ps", "-q"]).split()
    if not ids:
        return []
    return sorted(
        run(
            ["docker", "inspect", "--format", "{{.Id}} {{.State.StartedAt}}", *ids]
        ).splitlines()
    )


def execute(candidate, apply=False):
    require(os.geteuid() == 0, "root_required_for_quorum_upgrade")
    require((ROOT / "current").is_symlink(), "existing_quorum_release_required")
    candidate = release_path(candidate)
    previous = release_path((ROOT / "current").resolve())
    require(previous != candidate, "release_already_selected")
    env = {**os.environ, **read_environment(ENV)}
    require(
        not env.get("QUORUM_SNAPSHOT_ROOT")
        and env.get("QUORUM_ENABLE_SNAPSHOT_PUBLICATION") != "1",
        "inherited_publication_must_remain_disabled",
    )
    require(
        run(["systemctl", "is-active", *UNITS]).splitlines() == ["active", "active"],
        "quorum_services_not_active",
    )
    ports = run(["ss", "-H", "-ltn", "( sport = :3017 or sport = :8017 )"]).splitlines()
    require(
        len(ports) == 2 and all("127.0.0.1:" in line for line in ports),
        "quorum_ports_not_loopback",
    )
    require(shutil.disk_usage(ROOT).free > 512 * 1024**2, "insufficient_disk")
    mem = dict(
        line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines()
    )
    require(
        int(mem["MemAvailable"].split()[0]) > 200 * 1024,
        "insufficient_runtime_headroom",
    )
    additions = additive_requirements(
        previous / "backend/requirements.txt", candidate / "backend/requirements.txt"
    )
    python = str(ROOT / "venv/bin/python")
    installed = json.loads(
        run(
            [
                python,
                "-c",
                'import json,importlib.metadata as m; print(json.dumps({d.metadata["Name"].lower().replace("_","-"):d.version for d in m.distributions()}))',
            ]
        )
    )
    require(
        all(
            installed.get(k) == v
            for k, v in pins(previous / "backend/requirements.txt").items()
        ),
        "existing_environment_drift",
    )
    require(
        all(k not in installed or installed[k] == v for k, v in additions.items()),
        "new_dependency_conflicts_with_existing_environment",
    )
    before_workloads = workloads()
    if not apply:
        print(
            json.dumps(
                {
                    "ready_for_guarded_apply": True,
                    "previous": previous.name,
                    "candidate": candidate.name,
                    "additive_dependencies": additions,
                    "migrations_permitted": False,
                    "publishing_enabled": False,
                }
            )
        )
        return
    backup = (
        DATA
        / "backups"
        / ("upgrade-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    )
    backup.mkdir(mode=0o700, parents=True)
    backup_database(DATA / "portal.sqlite3", backup / "portal.sqlite3")
    (backup / "rollback.json").write_text(
        json.dumps(
            {
                "previous": str(previous),
                "candidate": str(candidate),
                "revision": (candidate / "REVISION").read_text().strip(),
            }
        )
    )
    (backup / "rollback.json").chmod(0o600)
    # Existing pinned distributions cannot be replaced. Old release remains compatible.
    missing = [k + "==" + v for k, v in additions.items() if k not in installed]
    if missing:
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--disable-pip-version-check",
                *missing,
            ]
        )
    run([python, "-m", "pip", "check"])
    account = pwd.getpwnam("quorum")

    def manage(*args):
        return run(
            [python, str(candidate / "backend/manage.py"), *args],
            env=env,
            cwd=candidate / "backend",
            user=account.pw_uid,
            group=account.pw_gid,
        )

    # Check Python 3.10 / installed wheels against a separate disposable test database.
    with tempfile.TemporaryDirectory(
        prefix="quorum-release-test-", dir=DATA
    ) as test_data:
        os.chown(test_data, account.pw_uid, account.pw_gid)
        test_env = {
            **env,
            "DJANGO_DEBUG": "1",
            "QUORUM_PORTAL_DATA": test_data,
            "QUORUM_CATALOG_PATH": "",
        }
        run(
            [
                python,
                str(candidate / "backend/manage.py"),
                "test",
                "portal",
                "--verbosity",
                "0",
            ],
            env=test_env,
            cwd=candidate / "backend",
            user=account.pw_uid,
            group=account.pw_gid,
        )
    manage("check", "--deploy")
    manage(
        "migrate", "--check"
    )  # Check only: this upgrade path never applies migrations.
    stopped = False
    switched = False
    try:
        stopped = True
        run(["systemctl", "stop", *UNITS])
        # Final consistent cutover backup and preservation baseline, after writes stop.
        backup_database(DATA / "portal.sqlite3", backup / "cutover.sqlite3")
        before_auth = fingerprint(DATA / "portal.sqlite3")
        shutil.copytree(ROOT / "static", backup / "static")
        run(
            [
                python,
                str(candidate / "backend/manage.py"),
                "collectstatic",
                "--noinput",
            ],
            env=env,
        )
        switch(candidate)
        switched = True
        require(
            fingerprint(DATA / "portal.sqlite3") == before_auth,
            "auth_data_changed_before_start",
        )
        run(["systemctl", "start", *UNITS])
        health()
        require(
            fingerprint(DATA / "portal.sqlite3") == before_auth,
            "auth_data_changed_during_release",
        )
        require(workloads() == before_workloads, "unrelated_container_state_changed")
        print(
            json.dumps(
                {
                    "deployed": candidate.name,
                    "rollback_target": previous.name,
                    "private_backup": str(backup),
                    "auth_preserved": True,
                    "publication_enabled": False,
                }
            )
        )
    except Exception:
        if stopped:
            run(["systemctl", "stop", *UNITS])
            if switched:
                switch(previous)
            if (backup / "static").exists():
                shutil.copytree(backup / "static", ROOT / "static", dirs_exist_ok=True)
            run(["systemctl", "start", *UNITS])
            health()
        # Never auto-restore auth DB: migrations were forbidden; retain concurrent user writes.
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up and switch only existing Quorum services",
    )
    args = parser.parse_args()
    try:
        if args.apply:
            with (ROOT / "upgrade.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                execute(args.release, True)
        else:
            execute(args.release)
    except Exception as error:
        print(
            "Upgrade refused or rolled back: "
            + (str(error) if isinstance(error, RuntimeError) else "operation_failed"),
            file=__import__("sys").stderr,
        )
        raise SystemExit(1)
