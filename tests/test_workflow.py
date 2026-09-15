"""Policy and transaction tests with an in-memory phone; never run ADB."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from healthier_notifications import cli
from healthier_notifications.android import DeviceError
from healthier_notifications.model import (
    PolicyError, build_plan, digest, identity, manual_rules, manual_status,
    utc_now, validate_policy,
)


FIRST = "com.example.shopping"
SECOND = "com.example.games"
EXTRA = "com.example.newapp"


def policy_for(*packages, phone="block", watch="block"):
    return {
        "schema_version": 1,
        "manual_review_days": 30,
        "schedule": {"timezone": "Europe/Warsaw", "work_hours": {
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "start": "10:14", "end": "18:14",
        }},
        "apps": [{"package": pkg, "label": pkg, "category": "noise",
                  "phone": phone, "watch": watch, "reviewed": True}
                 for pkg in packages],
        "manual_rules": [{"id": "delivery", "device": "both",
                          "instruction": "Test a direct message on both devices."}],
    }


def snapshot_for(*packages, granted=True):
    return {
        "schema_version": 1, "captured_at": utc_now(), "warnings": [],
        "device": {
            "serial": "PRIVATE-SERIAL", "user": 0,
            "fingerprint": "PRIVATE-OS-FINGERPRINT", "sdk": 35,
            "manufacturer": "Google", "model": "Pixel", "android": "15",
            "roles_verified": True,
        },
        "packages": {pkg: {
            "uid": 10123 + index, "version_code": "42",
            "system": False, "protected": False, "requests_notifications": True,
            "permission": {"granted": granted, "flags": ["USER_SET"]},
        } for index, pkg in enumerate(packages)},
    }


def attestations_for(policy, snapshot, result="pass", checked_at=None):
    return {rule["id"]: {
        "result": result, "checked_at": checked_at or utc_now(),
        "policy_hash": digest(policy), "device": identity(snapshot),
        "note": "PRIVATE FREE TEXT NOTE",
    } for rule in manual_rules(policy)}


class FakeDevice:
    """Return copies of phone state and make permission writes observable."""

    def __init__(self, snapshot):
        self.current = deepcopy(snapshot)
        self.writes = []
        self.snapshots = []
        self.before_write = None
        self.before_snapshot = None
        self.fail_write = None
        self.fail_after_write = False

    def snapshot(self, packages=None):
        self.snapshots.append(deepcopy(packages))
        if self.before_snapshot:
            self.before_snapshot(self, packages)
        value = deepcopy(self.current)
        if packages is not None:
            for package, app in value["packages"].items():
                if package not in packages:
                    app.update(version_code=None, requests_notifications=False,
                               permission={"granted": None, "flags": []})
        value["inspected_packages"] = list(value["packages"]) if packages is None else [
            package for package in packages if package in value["packages"]]
        return value

    def set_permission(self, package, granted):
        if self.before_write:
            self.before_write(package, granted)
        self.writes.append((package, granted))
        fails = len(self.writes) == self.fail_write
        if fails and not self.fail_after_write:
            raise DeviceError("Simulated ADB failure before mutation")
        self.current["packages"][package]["permission"]["granted"] = granted
        if fails:
            raise DeviceError("Simulated timeout after successful device mutation")


class TemporaryWorkflowCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = self.root / ".local"
        self.output = io.StringIO()
        stdout = redirect_stdout(self.output)
        stderr = redirect_stderr(self.output)
        stdout.__enter__()
        stderr.__enter__()
        self.addCleanup(stdout.__exit__, None, None, None)
        self.addCleanup(stderr.__exit__, None, None, None)

    def journal(self):
        paths = list((self.local / "transactions").glob("*.json"))
        self.assertEqual(len(paths), 1)
        return paths[0], cli.read_json(paths[0])

    def apply(self, device, policy=None, baseline=None):
        return cli.apply_plan(device, policy or policy_for(FIRST),
                              baseline or snapshot_for(FIRST), self.local)


class ApplyTests(TemporaryWorkflowCase):
    def test_success_writes_ahead_of_each_mutation_and_verifies(self):
        baseline = snapshot_for(FIRST, SECOND)
        device = FakeDevice(baseline)

        def check_durable_attempt(package, granted):
            _, journal = self.journal()
            row = next(c for c in journal["changes"] if c["package"] == package)
            self.assertTrue(row["attempted"])
            self.assertEqual(row["before"]["granted"], True)
            self.assertEqual(journal["state"], "in-progress")
            self.assertTrue((self.local / "mutation.lock").exists())

        device.before_write = check_durable_attempt
        path = self.apply(device, policy_for(FIRST, SECOND), baseline)
        journal = cli.read_json(path)
        self.assertEqual(device.writes, [(FIRST, False), (SECOND, False)])
        self.assertEqual(journal["state"], "applied")
        self.assertEqual(journal["device"], identity(baseline))
        self.assertEqual(journal["policy_hash"], digest(policy_for(FIRST, SECOND)))
        self.assertTrue(all(c.get("verified_at") for c in journal["changes"]))
        self.assertTrue(all(c["observed_after"] == {"granted": False, "flags": ["USER_SET"]}
                            for c in journal["changes"]))
        self.assertFalse((self.local / "mutation.lock").exists())

    def test_permission_already_matches_has_no_writes_or_journal(self):
        baseline = snapshot_for(FIRST, granted=False)
        device = FakeDevice(baseline)
        self.assertIsNone(self.apply(device, baseline=baseline))
        self.assertEqual(device.writes, [])
        self.assertFalse((self.local / "transactions").exists())

    def test_any_planned_blocker_prevents_all_writes(self):
        baseline = snapshot_for(FIRST, SECOND)
        baseline["packages"][SECOND]["permission"]["granted"] = None
        device = FakeDevice(baseline)
        with self.assertRaises(PolicyError):
            self.apply(device, policy_for(FIRST, SECOND), baseline)
        self.assertEqual(device.writes, [])
        self.assertFalse((self.local / "transactions").exists())

    def test_unsafe_or_unknown_baseline_never_writes(self):
        mutations = {
            "system": lambda s: s["packages"][FIRST].update(system=True),
            "unknown-system": lambda s: s["packages"][FIRST].pop("system"),
            "protected": lambda s: s["packages"][FIRST].update(protected=True),
            "unknown-protection": lambda s: s["packages"][FIRST].pop("protected"),
            "unknown-permission": lambda s: s["packages"][FIRST]["permission"].update(granted=None),
            "missing-manifest-permission": lambda s: s["packages"][FIRST].update(requests_notifications=False),
            "missing-uid": lambda s: s["packages"][FIRST].update(uid=None),
            "missing-version": lambda s: s["packages"][FIRST].update(version_code=None),
            "roles-unverified": lambda s: s["device"].update(roles_verified=False),
            "old-android": lambda s: s["device"].update(sdk=32),
            "not-installed": lambda s: s["packages"].pop(FIRST),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                baseline = snapshot_for(FIRST)
                mutation(baseline)
                device = FakeDevice(baseline)
                with self.assertRaises(PolicyError):
                    self.apply(device, baseline=baseline)
                self.assertEqual(device.writes, [])

    def test_every_fixed_flag_blocks_apply(self):
        for flag in ("USER_FIXED", "POLICY_FIXED", "SYSTEM_FIXED", "OEM_FIXED"):
            with self.subTest(flag=flag):
                baseline = snapshot_for(FIRST)
                baseline["packages"][FIRST]["permission"]["flags"] = [flag]
                device = FakeDevice(baseline)
                with self.assertRaises(PolicyError):
                    self.apply(device, baseline=baseline)
                self.assertEqual(device.writes, [])

    def test_device_user_and_fingerprint_drift_prevent_writes(self):
        for key, value in (("serial", "OTHER"), ("user", 10), ("fingerprint", "NEW BUILD")):
            with self.subTest(key=key):
                device = FakeDevice(snapshot_for(FIRST))
                device.current["device"][key] = value
                with self.assertRaises(PolicyError):
                    self.apply(device)
                self.assertEqual(device.writes, [])

    def test_package_uid_version_permission_or_flags_drift_prevent_writes(self):
        mutations = [lambda a: a.update(uid=99999), lambda a: a.update(version_code="43"),
                     lambda a: a["permission"].update(granted=False),
                     lambda a: a["permission"].update(flags=[])]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                device = FakeDevice(snapshot_for(FIRST))
                mutation(device.current["packages"][FIRST])
                with self.assertRaises(PolicyError):
                    self.apply(device)
                self.assertEqual(device.writes, [])

    def test_live_protection_changes_prevent_writes(self):
        for key, value in (("system", True), ("protected", True), ("requests_notifications", False)):
            with self.subTest(key=key):
                device = FakeDevice(snapshot_for(FIRST))
                device.current["packages"][FIRST][key] = value
                with self.assertRaises(PolicyError):
                    self.apply(device)
                self.assertEqual(device.writes, [])

    def test_live_role_lookup_failure_prevents_writes(self):
        device = FakeDevice(snapshot_for(FIRST))
        device.current["device"]["roles_verified"] = False
        with self.assertRaises(PolicyError):
            self.apply(device)
        self.assertEqual(device.writes, [])

    def test_all_packages_are_preflighted_before_the_first_write(self):
        baseline = snapshot_for(FIRST, SECOND)
        device = FakeDevice(baseline)
        device.current["packages"][SECOND]["version_code"] = "43"
        with self.assertRaises(PolicyError):
            self.apply(device, policy_for(FIRST, SECOND), baseline)
        self.assertEqual(device.writes, [], "An existing blocker in app #2 must not permit an app #1 write")

    def test_partial_failure_preserves_attempts_and_successful_prior_write(self):
        baseline = snapshot_for(FIRST, SECOND)
        device = FakeDevice(baseline)
        device.fail_write = 2
        with self.assertRaises(DeviceError):
            self.apply(device, policy_for(FIRST, SECOND), baseline)
        _, journal = self.journal()
        self.assertEqual(journal["state"], "incomplete")
        self.assertTrue(all(c["attempted"] for c in journal["changes"]))
        self.assertIn("verified_at", journal["changes"][0])
        self.assertNotIn("verified_at", journal["changes"][1])
        self.assertFalse(device.current["packages"][FIRST]["permission"]["granted"])
        self.assertTrue(device.current["packages"][SECOND]["permission"]["granted"])
        self.assertFalse((self.local / "mutation.lock").exists())

    def test_successful_write_followed_by_timeout_is_recoverable(self):
        device = FakeDevice(snapshot_for(FIRST))
        device.fail_write = 1
        device.fail_after_write = True
        with self.assertRaises(DeviceError):
            self.apply(device)
        path, journal = self.journal()
        self.assertEqual(journal["state"], "incomplete")
        self.assertTrue(journal["changes"][0]["attempted"])
        self.assertNotIn("observed_after", journal["changes"][0])
        self.assertFalse(device.current["packages"][FIRST]["permission"]["granted"])
        device.fail_write = None
        cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [(FIRST, False), (FIRST, True)])
        self.assertEqual(cli.read_json(path)["state"], "restored")

    def test_verification_flag_change_is_recorded_as_incomplete(self):
        device = FakeDevice(snapshot_for(FIRST))

        def alter_flags_after_write(fake, packages):
            if fake.writes:
                fake.current["packages"][FIRST]["permission"]["flags"].append("USER_SENSITIVE_WHEN_DENIED")

        device.before_snapshot = alter_flags_after_write
        with self.assertRaises(PolicyError):
            self.apply(device)
        _, journal = self.journal()
        self.assertEqual(journal["state"], "incomplete")
        self.assertIn("USER_SENSITIVE_WHEN_DENIED", journal["changes"][0]["observed_after"]["flags"])

    def test_existing_mutation_lock_prevents_writes(self):
        self.local.mkdir()
        lock = self.local / "mutation.lock"
        lock.write_text("999", encoding="utf-8")
        device = FakeDevice(snapshot_for(FIRST))
        with self.assertRaisesRegex(PolicyError, "Another mutation"):
            self.apply(device)
        self.assertEqual(device.writes, [])
        self.assertEqual(lock.read_text(encoding="utf-8"), "999")

    def test_failed_write_ahead_journal_prevents_device_mutation(self):
        device = FakeDevice(snapshot_for(FIRST))
        real_write_json = cli.write_json
        calls = 0

        def fail_recording_attempt(path, value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Simulated disk full before durable attempted marker")
            return real_write_json(path, value)

        with patch.object(cli, "write_json", side_effect=fail_recording_attempt):
            with self.assertRaises(OSError):
                self.apply(device)
        self.assertEqual(device.writes, [])
        self.assertTrue(device.current["packages"][FIRST]["permission"]["granted"])
        self.assertEqual(self.journal()[1]["state"], "incomplete")
        self.assertFalse((self.local / "mutation.lock").exists())


class RestoreTests(TemporaryWorkflowCase):
    def applied(self, *packages):
        baseline = snapshot_for(*packages)
        device = FakeDevice(baseline)
        path = self.apply(device, policy_for(*packages), baseline)
        device.writes.clear()
        return device, path

    def test_preview_has_no_device_or_journal_mutation(self):
        device, path = self.applied(FIRST)
        before = path.read_bytes()
        cli.restore_transaction(device, path, self.local)
        self.assertEqual(device.writes, [])
        self.assertEqual(path.read_bytes(), before)

    def test_restore_runs_in_reverse_and_second_restore_is_idempotent(self):
        device, path = self.applied(FIRST, SECOND)

        def check_restore_journal(package, granted):
            journal = cli.read_json(path)
            self.assertEqual(journal["restore_pending"], package)
            self.assertIn("restore_started_at", journal)

        device.before_write = check_restore_journal
        cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [(SECOND, True), (FIRST, True)])
        journal = cli.read_json(path)
        self.assertEqual(journal["state"], "restored")
        self.assertEqual(set(journal["restored_packages"]), {FIRST, SECOND})
        self.assertNotIn("restore_pending", journal)
        self.assertEqual([c["before"]["granted"] for c in journal["changes"]], [True, True])
        device.writes.clear()
        cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [])

    def test_restore_refuses_later_permission_flag_edit_before_any_write(self):
        device, path = self.applied(FIRST, SECOND)
        device.current["packages"][FIRST]["permission"]["flags"].append("USER_SENSITIVE_WHEN_DENIED")
        with self.assertRaisesRegex(PolicyError, "differs from both"):
            cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [])

    def test_restore_refuses_reinstalled_or_updated_package_before_any_write(self):
        device, path = self.applied(FIRST, SECOND)
        saved = deepcopy(device.current)
        for key, value in (("uid", 22222), ("version_code", "99")):
            with self.subTest(key=key):
                device.current = deepcopy(saved)
                device.current["packages"][FIRST][key] = value
                with self.assertRaisesRegex(PolicyError, "package identity"):
                    cli.restore_transaction(device, path, self.local, execute=True)
                self.assertEqual(device.writes, [])

    def test_restore_refuses_wrong_device_user_and_os_build(self):
        device, path = self.applied(FIRST)
        saved = deepcopy(device.current)
        for key, value in (("serial", "OTHER"), ("user", 10), ("fingerprint", "NEW")):
            with self.subTest(key=key):
                device.current = deepcopy(saved)
                device.current["device"][key] = value
                with self.assertRaisesRegex(PolicyError, "original device"):
                    cli.restore_transaction(device, path, self.local, execute=True)
                self.assertEqual(device.writes, [])

    def test_restore_refuses_unknown_system_protected_and_role_failure(self):
        device, path = self.applied(FIRST)
        saved = deepcopy(device.current)
        mutations = [lambda s: s["packages"][FIRST].update(system=True),
                     lambda s: s["packages"][FIRST].update(protected=True),
                     lambda s: s["device"].update(roles_verified=False),
                     lambda s: s["packages"][FIRST]["permission"].update(granted=None)]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                device.current = deepcopy(saved)
                mutation(device.current)
                with self.assertRaises(PolicyError):
                    cli.restore_transaction(device, path, self.local, execute=True)
                self.assertEqual(device.writes, [])

    def test_restore_rechecks_precondition_immediately_before_write(self):
        device, path = self.applied(FIRST)
        count = 0

        def change_after_preview(fake, packages):
            nonlocal count
            count += 1
            if count == 2:
                fake.current["packages"][FIRST]["permission"]["flags"].append("USER_FIXED")

        device.before_snapshot = change_after_preview
        with self.assertRaises(PolicyError):
            cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [])
        self.assertEqual(cli.read_json(path)["state"], "restore-incomplete")

    def test_restore_timeout_after_success_can_be_retried_without_second_write(self):
        device, path = self.applied(FIRST)
        device.fail_write = 1
        device.fail_after_write = True
        with self.assertRaises(DeviceError):
            cli.restore_transaction(device, path, self.local, execute=True)
        journal = cli.read_json(path)
        self.assertEqual(journal["state"], "restore-incomplete")
        self.assertEqual(journal["restore_pending"], FIRST)
        self.assertTrue(device.current["packages"][FIRST]["permission"]["granted"])
        device.fail_write = None
        cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [(FIRST, True)])
        self.assertEqual(cli.read_json(path)["state"], "restored")
        self.assertNotIn("restore_pending", cli.read_json(path))

    def test_partial_restore_retry_only_writes_the_unrestored_package(self):
        device, path = self.applied(FIRST, SECOND)
        device.fail_write = 2
        with self.assertRaises(DeviceError):
            cli.restore_transaction(device, path, self.local, execute=True)
        journal = cli.read_json(path)
        self.assertEqual(journal["state"], "restore-incomplete")
        self.assertEqual(set(journal["restored_packages"]), {SECOND})
        self.assertEqual(journal["restore_pending"], FIRST)
        self.assertEqual(device.writes, [(SECOND, True), (FIRST, True)])
        self.assertTrue(device.current["packages"][SECOND]["permission"]["granted"])
        self.assertFalse(device.current["packages"][FIRST]["permission"]["granted"])
        device.fail_write = None
        device.writes.clear()
        cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [(FIRST, True)])
        self.assertEqual(cli.read_json(path)["state"], "restored")

    def test_unattempted_changes_are_not_restored(self):
        device, path = self.applied(FIRST)
        journal = cli.read_json(path)
        journal["changes"][0]["attempted"] = False
        cli.write_json(path, journal)
        cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.writes, [])

    def test_invalid_journal_package_is_rejected_before_device_access(self):
        device, path = self.applied(FIRST)
        journal = cli.read_json(path)
        journal["changes"][0]["package"] = "com.example;reboot"
        cli.write_json(path, journal)
        device.snapshots.clear()
        with self.assertRaises(PolicyError):
            cli.restore_transaction(device, path, self.local, execute=True)
        self.assertEqual(device.snapshots, [])
        self.assertEqual(device.writes, [])


class PolicyTests(unittest.TestCase):
    def test_local_only_accepts_booleans_or_absence(self):
        policy = policy_for(FIRST)
        self.assertNotIn("local_only", validate_policy(policy))
        for value in (True, False):
            with self.subTest(value=value):
                policy["local_only"] = value
                self.assertIs(validate_policy(policy)["local_only"], value)

    def test_local_only_rejects_non_booleans(self):
        for value in (None, 0, 1, "true", "false", "", [], [True], {}):
            with self.subTest(value=value):
                policy = policy_for(FIRST)
                policy["local_only"] = value
                with self.assertRaisesRegex(PolicyError, "local_only must be true or false"):
                    validate_policy(policy)

    def test_user_work_schedule_is_accepted_without_rounding(self):
        policy = validate_policy(policy_for(FIRST))
        self.assertEqual(policy["schedule"]["work_hours"]["start"], "10:14")
        self.assertEqual(policy["schedule"]["work_hours"]["end"], "18:14")

    def test_shell_injection_package_names_are_rejected(self):
        for package in ("com.example;reboot", "$(reboot)", "com.example app", "--help",
                        "com.example\nreboot", "com.example`reboot`", "com.example\0app"):
            with self.subTest(package=package):
                with self.assertRaises(PolicyError):
                    validate_policy(policy_for(package))

    def test_unreviewed_mutations_and_block_phone_allow_watch_are_rejected(self):
        for phone, watch, reviewed in (("block", "block", False), ("allow", "review", False),
                                       ("block", "allow", True)):
            with self.subTest(phone=phone, watch=watch, reviewed=reviewed):
                policy = policy_for(FIRST, phone=phone, watch=watch)
                policy["apps"][0]["reviewed"] = reviewed
                with self.assertRaises(PolicyError):
                    validate_policy(policy)

    def test_communicators_calls_work_and_safety_cannot_be_whole_app_blocked(self):
        for category in ("messages", "calls", "work", "safety", "security", "reminders", "other"):
            with self.subTest(category=category):
                policy = policy_for(FIRST)
                policy["apps"][0]["category"] = category
                with self.assertRaises(PolicyError):
                    validate_policy(policy)

    def test_unreviewed_preserve_rule_is_read_only(self):
        policy = policy_for(FIRST, phone="preserve", watch="review")
        policy["apps"][0]["reviewed"] = False
        self.assertEqual(build_plan(policy, snapshot_for(FIRST))["changes"], [])

    def test_duplicate_packages_and_reserved_or_duplicate_manual_ids_are_rejected(self):
        bad = []
        policy = policy_for(FIRST, FIRST)
        bad.append(policy)
        policy = policy_for(FIRST)
        policy["manual_rules"].append(deepcopy(policy["manual_rules"][0]))
        bad.append(policy)
        policy = policy_for(FIRST)
        policy["manual_rules"][0]["id"] = "app:reserved"
        bad.append(policy)
        for index, policy in enumerate(bad):
            with self.subTest(index=index), self.assertRaises(PolicyError):
                validate_policy(policy)

    def test_invalid_schedule_and_review_window_are_rejected(self):
        for field, value in (("start", "25:14"), ("end", "18:60"), ("days", []), ("days", ["Monday"])):
            with self.subTest(field=field, value=value):
                policy = policy_for(FIRST)
                policy["schedule"]["work_hours"][field] = value
                with self.assertRaises(PolicyError):
                    validate_policy(policy)
        for value in (True, 0, 366, "30"):
            with self.subTest(value=value):
                policy = policy_for(FIRST)
                policy["manual_review_days"] = value
                with self.assertRaises(PolicyError):
                    validate_policy(policy)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.policy = policy_for(FIRST)
        self.snapshot = snapshot_for(FIRST, granted=False)
        self.entries = attestations_for(self.policy, self.snapshot)

    def test_alignment_requires_fresh_observation_and_all_manual_passes(self):
        report = cli.status_report(self.policy, self.snapshot, self.entries)
        self.assertEqual(report["status"], "observed-and-manually-checked")
        self.assertEqual(report["manual_checks_pending"], 0)
        self.assertTrue(all(c["status"] == "self-reported-pass" for c in report["manual_checks"]))
        self.assertIn("No live Garmin telemetry", report["scope"])
        self.assertEqual(cli.status_report(self.policy, self.snapshot, {})["status"], "needs-review")

    def test_old_future_invalid_and_naive_snapshots_are_never_fresh(self):
        now = datetime.now(timezone.utc)
        for captured in ((now - timedelta(hours=25)).isoformat(),
                         (now + timedelta(hours=1)).isoformat(), "not-a-date", "2026-09-15T10:00:00"):
            with self.subTest(captured=captured):
                self.snapshot["captured_at"] = captured
                report = cli.status_report(self.policy, self.snapshot, self.entries)
                self.assertFalse(report["observation_fresh"])
                self.assertEqual(report["status"], "needs-review")

    def test_manual_attestations_expire_and_are_bound_to_policy_device_user_and_build(self):
        changes = [lambda e: e.update(policy_hash="wrong"),
                   lambda e: e["device"].update(serial="other"),
                   lambda e: e["device"].update(user=10),
                   lambda e: e["device"].update(fingerprint="new-build"),
                   lambda e: e.update(checked_at=(datetime.now(timezone.utc) - timedelta(days=31)).isoformat()),
                   lambda e: e.update(checked_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
                   lambda e: e.update(checked_at="bad-date")]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                entries = deepcopy(self.entries)
                change(entries["delivery"])
                checks = manual_status(self.policy, self.snapshot, entries)
                self.assertEqual(next(c for c in checks if c["id"] == "delivery")["status"], "stale")
                self.assertEqual(cli.status_report(self.policy, self.snapshot, entries)["status"], "needs-review")

    def test_manual_failure_is_reported_as_self_reported_failure(self):
        self.entries["delivery"]["result"] = "fail"
        checks = manual_status(self.policy, self.snapshot, self.entries)
        self.assertEqual(checks[0]["status"], "self-reported-fail")
        self.assertEqual(cli.status_report(self.policy, self.snapshot, self.entries)["status"], "needs-review")

    def test_curated_report_omits_device_identifiers_and_private_notes(self):
        self.policy["apps"][0]["note"] = "PRIVATE POLICY NOTE"
        self.entries = attestations_for(self.policy, self.snapshot)
        self.snapshot["warnings"] = ["PRIVATE RAW WARNING"]
        report = cli.status_report(self.policy, self.snapshot, self.entries)
        exported = json.dumps(report) + cli.report_markdown(report)
        for secret in ("PRIVATE-SERIAL", "PRIVATE-OS-FINGERPRINT", "PRIVATE FREE TEXT NOTE",
                       "PRIVATE POLICY NOTE", "PRIVATE RAW WARNING"):
            self.assertNotIn(secret, exported)
        self.assertNotIn("serial", report["device"])
        self.assertNotIn("fingerprint", report["device"])
        self.assertNotIn("user", report["device"])

    def test_unclassified_third_party_app_prevents_alignment(self):
        self.snapshot["packages"][EXTRA] = deepcopy(self.snapshot["packages"][FIRST])
        report = cli.status_report(self.policy, self.snapshot, self.entries)
        self.assertEqual(report["unclassified_third_party_apps"], 1)
        self.assertEqual(report["status"], "needs-review")

    def test_system_inventory_does_not_count_as_unclassified_third_party_app(self):
        self.snapshot["packages"]["android"] = {
            "uid": 1000, "system": True, "protected": True, "version_code": None,
            "requests_notifications": False, "permission": {"granted": None, "flags": []},
        }
        self.assertEqual(cli.status_report(self.policy, self.snapshot, self.entries)["unclassified_third_party_apps"], 0)

    def test_unreviewed_watch_choice_and_empty_policy_prevent_alignment(self):
        self.policy["apps"][0]["watch"] = "review"
        self.entries = attestations_for(self.policy, self.snapshot)
        report = cli.status_report(self.policy, self.snapshot, self.entries)
        self.assertEqual(report["status"], "needs-review")
        self.assertEqual(report["app_reviews_pending"], 1)
        empty = policy_for()
        self.assertEqual(cli.status_report(empty, snapshot_for(), attestations_for(empty, snapshot_for()))["status"], "needs-review")

    def test_preserved_permissions_remain_explicitly_unmanaged(self):
        self.policy["apps"][0]["phone"] = "preserve"
        report = cli.status_report(self.policy, self.snapshot, {})
        self.assertEqual(report["apps"][0]["status"], "unmanaged")


class MainTests(TemporaryWorkflowCase):
    def setUp(self):
        super().setUp()
        self.policy = policy_for(FIRST)
        self.policy_path = self.root / "policy.json"
        cli.write_json(self.policy_path, self.policy)
        self.args = ["--policy", str(self.policy_path), "--local-dir", str(self.local)]

    def test_apply_without_yes_only_previews(self):
        device = FakeDevice(snapshot_for(FIRST))
        with patch.object(cli, "device_for", return_value=device):
            result = cli.main(self.args + ["apply"])
        self.assertEqual(result, 0)
        self.assertEqual(device.writes, [])
        self.assertFalse((self.local / "transactions").exists())
        self.assertIn("Preview only", self.output.getvalue())

    def test_restore_without_yes_only_previews(self):
        device = FakeDevice(snapshot_for(FIRST))
        path = self.apply(device)
        device.writes.clear()
        before = path.read_bytes()
        with patch.object(cli, "device_for", return_value=device):
            result = cli.main(self.args + ["restore", str(path)])
        self.assertEqual(result, 0)
        self.assertEqual(device.writes, [])
        self.assertEqual(path.read_bytes(), before)

    def test_live_status_inventories_unconfigured_apps(self):
        device = FakeDevice(snapshot_for(FIRST, EXTRA, granted=False))
        cli.write_json(self.local / "manual-checks.json", attestations_for(self.policy, device.current))
        with patch.object(cli, "device_for", return_value=device):
            result = cli.main(self.args + ["status"])
        self.assertEqual(result, 2, "A newly installed unconfigured app must require review")
        self.assertIn("unclassified apps: 1", self.output.getvalue())
        self.assertEqual(device.writes, [])

    def test_local_only_export_is_rejected_before_observation_or_output(self):
        self.policy["local_only"] = True
        self.policy["apps"][0]["label"] = "PRIVATE APP LABEL"
        cli.write_json(self.policy_path, self.policy)
        state = self.root / "state"
        state.mkdir()
        for name in ("status.json", "status.md"):
            (state / name).write_text("Existing public summary", encoding="utf-8")
        for extra in ([], ["--snapshot", str(self.root / "not-read.json")]):
            with self.subTest(extra=extra), patch.object(cli, "device_for") as device, \
                    patch.object(cli, "status_report") as report, patch.object(cli, "ROOT", self.root):
                result = cli.main(self.args + ["status", "--export"] + extra)
            self.assertEqual(result, 1)
            device.assert_not_called()
            report.assert_not_called()
            self.assertNotIn("PRIVATE APP LABEL", self.output.getvalue())
            self.assertIn("local_only", self.output.getvalue())
            self.assertIn("without --export", self.output.getvalue())
            for name in ("status.json", "status.md"):
                self.assertEqual((state / name).read_text(encoding="utf-8"), "Existing public summary")
        self.assertFalse((self.local / "latest.json").exists())

    def test_local_only_status_without_export_remains_available(self):
        self.policy["local_only"] = True
        cli.write_json(self.policy_path, self.policy)
        device = FakeDevice(snapshot_for(FIRST, granted=False))
        with patch.object(cli, "device_for", return_value=device), patch.object(cli, "ROOT", self.root):
            result = cli.main(self.args + ["status"])
        self.assertEqual(result, 2)
        self.assertIn(FIRST, self.output.getvalue())
        self.assertFalse((self.root / "state").exists())
        self.assertEqual(device.writes, [])

    def test_init_marks_inventory_draft_local_only_without_changing_policy(self):
        original = self.policy_path.read_bytes()
        device = FakeDevice(snapshot_for(FIRST, EXTRA))
        with patch.object(cli, "device_for", return_value=device):
            result = cli.main(self.args + ["init"])
        self.assertEqual(result, 0)
        draft = cli.read_json(self.local / "policy.draft.json")
        self.assertIs(draft["local_only"], True)
        self.assertIn(EXTRA, {app["package"] for app in draft["apps"]})
        self.assertEqual(self.policy_path.read_bytes(), original)
        self.assertEqual(device.writes, [])

    def test_attest_stores_local_evidence_and_export_excludes_its_note(self):
        device = FakeDevice(snapshot_for(FIRST, granted=False))
        latest = self.local / "latest.json"
        cli.write_json(latest, snapshot_for(FIRST, EXTRA))
        existing_observation = latest.read_bytes()
        with patch.object(cli, "device_for", return_value=device):
            result = cli.main(self.args + ["attest", "delivery", "--result", "pass",
                                            "--note", "PRIVATE TEST MESSAGE AND WATCH DETAILS"])
        self.assertEqual(result, 0)
        self.assertEqual(latest.read_bytes(), existing_observation,
                         "Attesting identity must not replace the latest permission inventory")
        entry = cli.read_json(self.local / "manual-checks.json")["delivery"]
        self.assertEqual(entry["note"], "PRIVATE TEST MESSAGE AND WATCH DETAILS")
        self.assertEqual(entry["device"], identity(device.current))
        self.assertEqual(entry["policy_hash"], digest(self.policy))
        with patch.object(cli, "device_for", return_value=device), patch.object(cli, "ROOT", self.root):
            cli.main(self.args + ["status", "--export"])
        exported = (self.root / "state" / "status.json").read_text(encoding="utf-8")
        exported += (self.root / "state" / "status.md").read_text(encoding="utf-8")
        for secret in (entry["note"], "PRIVATE-SERIAL", "PRIVATE-OS-FINGERPRINT"):
            self.assertNotIn(secret, exported)
        self.assertEqual(device.writes, [])

    def test_unknown_attestation_id_is_rejected_without_device_access(self):
        with patch.object(cli, "device_for") as device:
            result = cli.main(self.args + ["attest", "does-not-exist", "--result", "pass"])
        self.assertEqual(result, 1)
        device.assert_not_called()

    def test_open_settings_reports_requested_target_without_claiming_ui_verification(self):
        for options, package, channel, target in (
            ([], None, None, "Requested notification settings."),
            (["--package", FIRST], FIRST, None, f"Requested notification settings for {FIRST}."),
            (["--package", FIRST, "--channel", "direct messages"], FIRST, "direct messages",
             f"Requested notification settings for {FIRST}, channel 'direct messages'."),
        ):
            with self.subTest(options=options), patch.object(cli, "device_for") as device:
                self.output.seek(0)
                self.output.truncate(0)
                result = cli.main(self.args + ["open-settings"] + options)
            self.assertEqual(result, 0)
            device.return_value.open_settings.assert_called_once_with(package, channel)
            output = self.output.getvalue()
            self.assertIn(target, output)
            self.assertIn("Confirm the displayed page, app and category", output)
            self.assertNotIn("Settings opened", output)

    def test_validate_and_offline_plan_do_not_connect_to_phone(self):
        path = self.root / "snapshot.json"
        cli.write_json(path, snapshot_for(FIRST))
        with patch.object(cli, "device_for") as device:
            self.assertEqual(cli.main(self.args + ["validate"]), 0)
            self.assertEqual(cli.main(self.args + ["plan", "--snapshot", str(path)]), 0)
        device.assert_not_called()


if __name__ == "__main__":
    unittest.main()
