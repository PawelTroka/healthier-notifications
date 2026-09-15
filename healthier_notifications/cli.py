"""Dependency-free CLI. All device changes are explicit and journaled."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from .android import AdbDevice, DeviceError
from .model import (PolicyError, app_identity, build_plan, digest, identity,
                    manual_rules, manual_status, mutation_problem, permission_state,
                    utc_now, validate_policy, validate_snapshot)

ROOT = Path(__file__).resolve().parent.parent


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PolicyError(f"Cannot read JSON at {path}: {exc}") from exc


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextmanager
def mutation_lock(local):
    local.mkdir(parents=True, exist_ok=True)
    path = local / "mutation.lock"
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise PolicyError(f"Another mutation may be running. Inspect {path}; remove it only after confirming that no apply/restore is active.") from exc
    try:
        with stream:
            stream.write(str(os.getpid()))
            stream.flush()
        yield
    finally:
        path.unlink(missing_ok=True)


def resolve_adb(explicit=None):
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found
    candidates = [ROOT / ".tools" / "platform-tools" / "adb.exe", ROOT / ".tools" / "platform-tools" / "adb"]
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(env):
            candidates.append(Path(os.environ[env]) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise PolicyError("ADB was not found. Extract Google's Android Platform Tools into .tools/platform-tools, add adb to PATH, or pass --adb PATH. See README.md.")


def device_for(args):
    return AdbDevice(adb=resolve_adb(args.adb), serial=args.serial, user=args.user)


def capture(device, local, packages=None):
    snapshot = validate_snapshot(device.snapshot(packages))
    write_json(local / "latest.json", snapshot)
    return snapshot


def display_plan(plan):
    for row in plan["apps"]:
        current = {True: "granted", False: "denied", None: "unknown"}.get(row.get("permission"), "unknown")
        print(f"{row['package']}: {current} -> {row['desired']} [{row['status']}]")
        if row["status"] in {"blocked", "missing"}:
            print(f"  {row['detail']}")
    print(f"\n{len(plan['changes'])} permission change(s); {len(plan['blocked'])} blocker(s).")


def check_precondition(baseline, live, change):
    if identity(baseline) != identity(live):
        raise PolicyError("Device, Android user or OS build changed since the plan. Scan again.")
    pkg = change["package"]
    app = live["packages"].get(pkg)
    if not app or app_identity(app) != change["identity"] or permission_state(app) != change["before"]:
        raise PolicyError(f"{pkg}: package or permission changed since the plan. Scan again.")
    problem = mutation_problem(live, app)
    if problem:
        raise PolicyError(f"{pkg}: {problem}")


def apply_plan(device, policy, baseline, local):
    """Write-ahead journal survives partial failures; never auto-roll back later user edits."""
    plan = build_plan(policy, baseline)
    if plan["blocked"]:
        raise PolicyError("Apply stopped before writing: resolve every blocker in the plan first.")
    if not plan["changes"]:
        return None
    local = Path(local)
    transaction = {
        "schema_version": 1, "kind": "notification-permissions", "id": uuid.uuid4().hex,
        "created_at": utc_now(), "device": identity(baseline), "policy_hash": digest(policy),
        "state": "in-progress", "changes": [{**c, "attempted": False} for c in plan["changes"]],
    }
    path = local / "transactions" / (transaction["id"] + ".json")
    with mutation_lock(local):
        preflight = device.snapshot([c["package"] for c in transaction["changes"]])
        for change in transaction["changes"]:
            check_precondition(baseline, preflight, change)
        write_json(path, transaction)
        print(f"Rollback journal: {path}", flush=True)
        try:
            for change in transaction["changes"]:
                pkg = change["package"]
                live = device.snapshot([pkg])
                check_precondition(baseline, live, change)
                change["attempted"] = True
                write_json(path, transaction)
                device.set_permission(pkg, change["after_granted"])
                after = device.snapshot([pkg])
                app = after["packages"].get(pkg)
                if identity(after) != transaction["device"] or not app or app_identity(app) != change["identity"]:
                    raise PolicyError(f"{pkg}: device/package identity changed during verification.")
                change["observed_after"] = permission_state(app)
                write_json(path, transaction)
                if change["observed_after"] != {"granted": change["after_granted"], "flags": change["before"]["flags"]}:
                    raise PolicyError(f"{pkg}: permission verification failed or flags changed. Inspect the journal and device settings.")
                change["verified_at"] = utc_now()
                write_json(path, transaction)
                print(f"Verified {pkg}: {'allowed' if change['after_granted'] else 'blocked'}")
            transaction["state"] = "applied"
        except BaseException as exc:
            transaction["state"] = "incomplete"
            transaction["error"] = str(exc) or type(exc).__name__
            write_json(path, transaction)
            raise
        write_json(path, transaction)
    return path


def restore_transaction(device, transaction_path, local, execute=False):
    path = Path(transaction_path)
    transaction = read_json(path)
    if not isinstance(transaction, dict) or transaction.get("schema_version") != 1 or transaction.get("kind") != "notification-permissions" or not isinstance(transaction.get("changes"), list):
        raise PolicyError("Not a supported rollback journal.")
    changes = transaction["changes"]
    if not changes:
        raise PolicyError("Journal has no changes.")
    # Journals are local data, not arbitrary command inputs.
    from .model import PACKAGE
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("package"), str) or not PACKAGE.fullmatch(change["package"]):
            raise PolicyError("Journal contains an invalid package.")
        if type(change.get("after_granted")) is not bool or type(change.get("before", {}).get("granted")) is not bool or not isinstance(change.get("before", {}).get("flags"), list):
            raise PolicyError("Journal contains an invalid permission baseline.")
    if len({c["package"] for c in changes}) != len(changes):
        raise PolicyError("Journal contains duplicate packages.")
    baseline = device.snapshot([c["package"] for c in changes])
    if identity(baseline) != transaction.get("device"):
        raise PolicyError("Restore requires the original device, Android user and OS build.")
    restore = []
    for change in reversed(changes):
        if not change.get("attempted"):
            continue
        pkg = change["package"]
        app = baseline["packages"].get(pkg)
        if not app or app_identity(app) != change.get("identity"):
            raise PolicyError(f"{pkg}: restore refused because package identity changed.")
        current = permission_state(app)
        if current == change["before"]:
            continue
        expected = {"granted": change["after_granted"], "flags": change["before"]["flags"]}
        if current != expected:
            raise PolicyError(f"{pkg}: state differs from both recorded baseline and intended change; inspect manually.")
        problem = mutation_problem(baseline, app)
        if problem:
            raise PolicyError(f"{pkg}: restore refused: {problem}")
        restore.append({"package": pkg, "identity": app_identity(app), "before": current, "after_granted": change["before"]["granted"]})
    for change in restore:
        print(f"Restore {change['package']} -> {'granted' if change['after_granted'] else 'denied'}")
    print(f"{len(restore)} permission(s) to restore.")
    if not execute:
        print("Preview only. Add --yes to restore this journal.")
        return
    with mutation_lock(Path(local)):
        # Retain the original journal and persist each restoration attempt in it.
        transaction["restore_started_at"] = utc_now()
        write_json(path, transaction)
        try:
            for change in restore:
                live = device.snapshot([change["package"]])
                check_precondition(baseline, live, change)
                transaction["restore_pending"] = change["package"]
                write_json(path, transaction)
                device.set_permission(change["package"], change["after_granted"])
                after = device.snapshot([change["package"]])
                app = after["packages"].get(change["package"])
                expected = {"granted": change["after_granted"], "flags": change["before"]["flags"]}
                if identity(after) != identity(baseline) or not app or app_identity(app) != change["identity"] or permission_state(app) != expected:
                    raise PolicyError(f"{change['package']}: restoration could not be verified.")
                transaction.setdefault("restored_packages", {})[change["package"]] = utc_now()
                transaction.pop("restore_pending", None)
                write_json(path, transaction)
            transaction["state"] = "restored"
            transaction["restored_at"] = utc_now()
            transaction.pop("restore_pending", None)
        except BaseException as exc:
            transaction["state"] = "restore-incomplete"
            transaction["restore_error"] = str(exc) or type(exc).__name__
            write_json(path, transaction)
            raise
        write_json(path, transaction)
    print("Recorded permission baseline restored and verified.")


def status_report(policy, snapshot, attestations):
    plan = build_plan(policy, snapshot)
    checks = manual_status(policy, snapshot, attestations)
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(snapshot["captured_at"])
        fresh = timedelta(0) <= age <= timedelta(hours=24)
    except (ValueError, TypeError):
        fresh = False
    configured = {a["package"] for a in policy["apps"]}
    unclassified = sum(1 for p, a in snapshot["packages"].items() if a.get("system") is False and p not in configured)
    app_reviews = sum(1 for a in policy["apps"] if not a["reviewed"] or a["watch"] == "review")
    pending = sum(c["status"] != "self-reported-pass" for c in checks)
    aligned = (bool(configured) and fresh and not plan["blocked"] and not plan["changes"] and not pending and not app_reviews and not unclassified
               and all(row["status"] != "missing" for row in plan["apps"]))
    device = snapshot["device"]
    return {
        "schema_version": 1, "generated_at": utc_now(), "observed_at": snapshot["captured_at"],
        "policy_hash": digest(policy), "device": {k: device.get(k) for k in ("manufacturer", "model", "android", "sdk")},
        "observation_fresh": fresh, "status": "observed-and-manually-checked" if aligned else "needs-review",
        "scope": "Android notification permission plus explicitly self-reported manual checks. No live Garmin telemetry or continuous synchronization.",
        "unclassified_third_party_apps": unclassified, "app_reviews_pending": app_reviews,
        "manual_checks_pending": pending, "permission_changes": len(plan["changes"]),
        "permission_blockers": len(plan["blocked"]), "apps": plan["apps"], "manual_checks": checks,
    }


def md_cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def report_markdown(report):
    lines = ["# Notification state", "", f"Status: **{report['status']}**", "",
             f"Observed: {report['observed_at']}. Fresh within 24 hours: {report['observation_fresh']}.", "",
             report["scope"], "", f"Permission changes: {report['permission_changes']}; blockers: {report['permission_blockers']}; manual checks pending: {report['manual_checks_pending']}; unclassified apps: {report['unclassified_third_party_apps']}.", "",
             "## Android notification permission", "", "| App | Desired | Observation | Watch policy |", "| --- | --- | --- | --- |"]
    for row in report["apps"]:
        lines.append(f"| {md_cell(row['label'])} | {row['desired']} | {row['status']} | {row['watch']} |")
    if not report["apps"]:
        lines.append("| No app rules configured | — | Needs inventory/review | — |")
    lines += ["", "## Manual checks", "", "| Check | Device | Result |", "| --- | --- | --- |"]
    for check in report["manual_checks"]:
        lines.append(f"| {check['id']} | {check['device']} | {check['status']} |")
    return "\n".join(lines) + "\n"


def make_parser():
    parser = argparse.ArgumentParser(description="Reviewable Android/Garmin notification policy. No device writes without apply/restore --yes.")
    parser.add_argument("--policy", type=Path, default=ROOT / "config" / "policy.json")
    parser.add_argument("--local-dir", type=Path, default=ROOT / ".local", help="Private snapshots/journals (default: repo .local)")
    parser.add_argument("--adb", help="Path to adb executable")
    parser.add_argument("--serial", help="Explicit authorized adb device serial")
    parser.add_argument("--user", type=int, help="Android user/profile ID; defaults to current user")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Validate policy offline")
    sub.add_parser("init", help="Read device inventory and create a private preserve-only policy draft")
    sub.add_parser("scan", help="Read device inventory and notification permissions into private .local/latest.json")
    plan = sub.add_parser("plan", help="Preview differences; never changes the device")
    plan.add_argument("--snapshot", type=Path, help="Use a saved snapshot offline instead of the phone")
    apply = sub.add_parser("apply", help="Preview or apply reviewed whole-app permission rules")
    apply.add_argument("--yes", action="store_true", help="Execute the displayed policy with live preflight and journaling")
    restore = sub.add_parser("restore", help="Preview or restore permission changes from a local journal")
    restore.add_argument("transaction", type=Path)
    restore.add_argument("--yes", action="store_true")
    status = sub.add_parser("status", help="Observe drift and manual verification state")
    status.add_argument("--snapshot", type=Path, help="Use a saved observation offline; its timestamp remains visible")
    status.add_argument("--export", action="store_true", help="Write curated state/status.json and state/status.md")
    settings = sub.add_parser("open-settings", help="Open phone notification settings for manual changes")
    settings.add_argument("--package")
    settings.add_argument("--channel", help="Known channel ID (do not guess from display label)")
    attest = sub.add_parser("attest", help="Record a manual check against the currently connected phone and current policy")
    attest.add_argument("rule_id")
    attest.add_argument("--result", required=True, choices=("pass", "fail"))
    attest.add_argument("--note", default="", help="Local-only note, e.g. tested watch model/firmware and outcome")
    sub.add_parser("checks", help="List manual checks and app watch choices without a device")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    try:
        local = args.local_dir.resolve()
        if args.command == "restore":
            restore_transaction(device_for(args), args.transaction, local, args.yes)
            return 0
        policy = validate_policy(read_json(args.policy))
        if args.command == "status" and args.export and policy.get("local_only", False):
            raise PolicyError("This policy is marked local_only. Run status without --export to keep the report local, or select the reviewed public config/policy.json for export.")
        if args.command == "validate":
            print(f"Policy valid: {len(policy['apps'])} app rule(s), {len(manual_rules(policy))} manual check(s).")
            if not policy["apps"]:
                print("No app permissions are configured yet. Run init when the phone is connected.")
            return 0
        if args.command == "checks":
            for rule in manual_rules(policy):
                print(f"{rule['id']} [{rule['device']}]\n  {rule['instruction']}\n")
            return 0
        if args.command == "open-settings":
            if args.channel and not args.package:
                raise PolicyError("--channel requires --package.")
            device_for(args).open_settings(args.package, args.channel)
            target = f"notification settings for {args.package}" if args.package else "notification settings"
            if args.channel:
                target += f", channel {args.channel!r}"
            print(f"Requested {target}. Confirm the displayed page, app and category before making changes. Changes made there require a fresh scan/manual check.")
            return 0
        if args.command == "attest":
            rules = {r["id"]: r for r in manual_rules(policy)}
            if args.rule_id not in rules:
                raise PolicyError("Unknown check. Run checks to see valid rule IDs.")
            # Identity-only read must not replace the last permission observation.
            snapshot = validate_snapshot(device_for(args).snapshot([]))
            path = local / "manual-checks.json"
            with mutation_lock(local):
                entries = read_json(path) if path.exists() else {}
                entries[args.rule_id] = {"result": args.result, "note": args.note, "checked_at": utc_now(), "policy_hash": digest(policy), "device": identity(snapshot)}
                write_json(path, entries)
            print(f"Recorded self-reported {args.result}: {args.rule_id}. This does not read or change watch settings.")
            return 0
        snapshot_path = getattr(args, "snapshot", None)
        if snapshot_path:
            snapshot = validate_snapshot(read_json(snapshot_path))
        else:
            device = device_for(args)
            packages = None if args.command in {"init", "scan"} else [a["package"] for a in policy["apps"]]
            snapshot = capture(device, local, packages)
        if args.command in {"init", "scan"}:
            print(f"Observed {snapshot['device'].get('manufacturer', '')} {snapshot['device'].get('model', '')}, Android {snapshot['device'].get('android', '?')}, user {snapshot['device']['user']}.")
            print(f"Private snapshot: {local / 'latest.json'} ({len(snapshot['packages'])} installed packages)")
            for warning in snapshot.get("warnings", []):
                print(f"Note: {warning}")
            if args.command == "init":
                draft = json.loads(json.dumps(policy))
                draft["local_only"] = True
                existing = {a["package"] for a in draft["apps"]}
                for pkg, app in sorted(snapshot["packages"].items()):
                    if app.get("system") is False and pkg not in existing:
                        draft["apps"].append({"package": pkg, "label": pkg, "category": "other", "phone": "preserve", "watch": "review", "reviewed": False, "note": "Identify this app. For communicators, keep DMs and calls; filter groups/reactions/promotions inside the app. Choose watch forwarding explicitly."})
                draft_path = local / "policy.draft.json"
                write_json(draft_path, draft)
                print(f"Private inventory draft: {draft_path}\nReview with --policy {draft_path}. Publish only deliberately selected app rules. Existing policy was not modified.")
            return 0
        if args.command in {"plan", "apply"}:
            plan = build_plan(policy, snapshot)
            display_plan(plan)
            print(f"{len(manual_rules(policy))} separate manual checks; use checks to list them.")
            if args.command == "apply" and args.yes:
                path = apply_plan(device, policy, snapshot, local)
                if path:
                    capture(device, local, [a["package"] for a in policy["apps"]])
                    print("Run status after completing the manual checks. Export is available for reviewed public policies only.")
                else:
                    print("No permission changes were needed. Manual checks remain separate.")
            else:
                print("Preview only. Use apply --yes to execute reviewed permission changes.")
            return 2 if plan["blocked"] else 0
        if args.command == "status":
            path = local / "manual-checks.json"
            entries = read_json(path) if path.exists() else {}
            report = status_report(policy, snapshot, entries)
            markdown = report_markdown(report)
            print(markdown)
            if args.export:
                write_json(ROOT / "state" / "status.json", report)
                (ROOT / "state" / "status.md").write_text(markdown, encoding="utf-8")
                print(f"Exported curated summary to {ROOT / 'state'}. Review before committing.")
            return 0 if report["status"] == "observed-and-manually-checked" else 2
        raise PolicyError("Unsupported command.")
    except (PolicyError, DeviceError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Any attempted permission writes have a journal in the local transactions directory.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
