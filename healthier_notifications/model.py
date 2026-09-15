"""Policy validation and pure comparisons; no device or filesystem writes."""

from datetime import datetime, timezone, timedelta
import hashlib
import json
import re

PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\Z")
RULE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}\Z")
CATEGORIES = {"calls", "messages", "work", "reminders", "safety", "security", "noise", "admin", "other"}


class PolicyError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def validate_policy(policy):
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise PolicyError("Policy must be a JSON object with schema_version 1.")
    if not isinstance(policy.get("apps"), list) or not isinstance(policy.get("manual_rules"), list):
        raise PolicyError("Policy requires apps and manual_rules arrays.")
    days = policy.get("manual_review_days", 30)
    if type(days) is not int or not 1 <= days <= 365:
        raise PolicyError("manual_review_days must be an integer from 1 to 365.")
    packages = set()
    for app in policy["apps"]:
        if not isinstance(app, dict):
            raise PolicyError("Each app rule must be an object.")
        pkg = app.get("package", "")
        if not isinstance(pkg, str) or not PACKAGE.fullmatch(pkg) or pkg in packages:
            raise PolicyError(f"Invalid or duplicate app package: {pkg!r}")
        packages.add(pkg)
        if not isinstance(app.get("category"), str) or app["category"] not in CATEGORIES:
            raise PolicyError(f"{pkg}: choose a valid category (see README).")
        if not isinstance(app.get("phone"), str) or app["phone"] not in {"preserve", "allow", "block"}:
            raise PolicyError(f"{pkg}: phone must be preserve, allow or block. Silent/category filtering is manual.")
        if not isinstance(app.get("watch"), str) or app["watch"] not in {"review", "allow", "block"}:
            raise PolicyError(f"{pkg}: watch must be review, allow or block.")
        if type(app.get("reviewed")) is not bool:
            raise PolicyError(f"{pkg}: reviewed must be true or false.")
        if app["phone"] != "preserve" and not app["reviewed"]:
            raise PolicyError(f"{pkg}: automated changes require reviewed: true.")
        if app["phone"] == "block" and app["category"] not in {"noise", "admin"}:
            raise PolicyError(f"{pkg}: whole-app blocking is restricted to reviewed noise/admin apps.")
        if app["phone"] == "block" and app["watch"] == "allow":
            raise PolicyError(f"{pkg}: a blocked phone app cannot be a reliable watch source.")
        for key in ("label", "note"):
            if key in app and not isinstance(app[key], str):
                raise PolicyError(f"{pkg}: {key} must be text.")
    ids = set()
    for rule in policy["manual_rules"]:
        if not isinstance(rule, dict):
            raise PolicyError("Each manual rule must be an object.")
        rule_id = rule.get("id", "")
        if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id) or rule_id in ids or rule_id.startswith("app:"):
            raise PolicyError(f"Invalid, reserved or duplicate manual rule id: {rule_id!r}")
        ids.add(rule_id)
        if not isinstance(rule.get("device"), str) or rule["device"] not in {"phone", "watch", "both"} or not isinstance(rule.get("instruction"), str) or not rule["instruction"].strip():
            raise PolicyError(f"{rule_id}: specify device and a nonempty instruction.")
    schedule = policy.get("schedule", {})
    if not isinstance(schedule, dict):
        raise PolicyError("schedule must be an object.")
    for key in ("work_hours", "sleep_hours"):
        hours = schedule.get(key)
        if hours is not None:
            if not isinstance(hours, dict) or not isinstance(hours.get("days"), list) or not hours["days"]:
                raise PolicyError(f"schedule.{key}: days, start and end are required.")
            if not all(isinstance(d, str) and d in {"mon", "tue", "wed", "thu", "fri", "sat", "sun"} for d in hours["days"]):
                raise PolicyError(f"schedule.{key}: invalid day.")
            for boundary in ("start", "end"):
                if not isinstance(hours.get(boundary), str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hours[boundary]):
                    raise PolicyError(f"schedule.{key}.{boundary}: use 24-hour HH:MM.")
    return policy


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise PolicyError("Unsupported snapshot format.")
    device = snapshot.get("device", {})
    if not isinstance(device, dict) or not all(k in device for k in ("serial", "user", "fingerprint", "sdk")):
        raise PolicyError("Snapshot lacks device identity.")
    if type(device["sdk"]) is not int or type(device["user"]) is not int or not isinstance(snapshot.get("packages"), dict):
        raise PolicyError("Snapshot has invalid SDK, Android user or packages.")
    if not isinstance(snapshot.get("captured_at"), str):
        raise PolicyError("Snapshot lacks observation time.")
    for pkg, app in snapshot["packages"].items():
        if not isinstance(app, dict) or not isinstance(app.get("permission"), dict):
            raise PolicyError(f"{pkg}: snapshot lacks permission metadata.")
        permission = app["permission"]
        if permission.get("granted") is not None and type(permission["granted"]) is not bool:
            raise PolicyError(f"{pkg}: invalid observed permission state.")
        if not isinstance(permission.get("flags"), list) or not all(isinstance(flag, str) for flag in permission["flags"]):
            raise PolicyError(f"{pkg}: invalid observed permission flags.")
    return snapshot


def identity(snapshot):
    dev = snapshot["device"]
    return {k: dev[k] for k in ("serial", "user", "fingerprint")}


def app_identity(app):
    return {k: app.get(k) for k in ("uid", "version_code")}


def permission_state(app):
    permission = app.get("permission", {})
    return {"granted": permission.get("granted"), "flags": sorted(permission.get("flags", []))}


def mutation_problem(snapshot, app):
    if snapshot["device"]["sdk"] < 33:
        return "Android 13/API 33 or later is required for this permission backend"
    if not snapshot["device"].get("roles_verified", False):
        return "default phone/SMS roles could not be verified"
    if app.get("system") is not False:
        return "system/preinstalled apps or unknown system status require manual review"
    if app.get("protected", True):
        return "protected communication, safety or companion app requires manual review"
    if app.get("shared_uid", False):
        return "multiple installed apps share this UID; review their permissions manually"
    if not app.get("requests_notifications"):
        return "POST_NOTIFICATIONS is not confirmed in the manifest"
    if type(app.get("permission", {}).get("granted")) is not bool:
        return "notification permission state is unknown"
    if app.get("uid") is None or app.get("version_code") is None:
        return "package identity is incomplete"
    if any("FIXED" in flag.upper() for flag in app.get("permission", {}).get("flags", [])):
        return "permission has a fixed flag; use device settings or your administrator"
    return None


def build_plan(policy, snapshot):
    validate_policy(policy)
    validate_snapshot(snapshot)
    result = {"changes": [], "blocked": [], "apps": []}
    for rule in policy["apps"]:
        pkg = rule["package"]
        app = snapshot["packages"].get(pkg)
        row = {"package": pkg, "label": rule.get("label", pkg), "desired": rule["phone"], "watch": rule["watch"]}
        if app is None:
            row.update(status="missing", permission=None, detail="Not installed for the selected Android user")
            if rule["phone"] != "preserve":
                result["blocked"].append({"package": pkg, "reason": row["detail"]})
        else:
            granted = app.get("permission", {}).get("granted")
            row["permission"] = granted
            if rule["phone"] == "preserve":
                row.update(status="unmanaged", detail="App permission is preserved; content/category filtering needs manual checks")
            elif type(granted) is bool and granted == (rule["phone"] == "allow"):
                row.update(status="permission-match", detail="Permission matches; delivery, categories and watch are separate checks")
            else:
                problem = mutation_problem(snapshot, app)
                if problem:
                    row.update(status="blocked", detail=problem)
                    result["blocked"].append({"package": pkg, "reason": problem})
                else:
                    row.update(status="permission-drift", detail="Explicit permission change is available")
                    result["changes"].append({"package": pkg, "identity": app_identity(app), "before": permission_state(app), "after_granted": rule["phone"] == "allow"})
        result["apps"].append(row)
    return result


def manual_rules(policy):
    rules = list(policy["manual_rules"])
    for app in policy["apps"]:
        if app["watch"] != "review":
            rules.append({"id": f"app:{app['package']}:watch", "device": "watch", "instruction": f"Verify Garmin Connect forwarding is {app['watch']} for {app.get('label', app['package'])} ({app['package']}). Test the actual watch result."})
    return rules


def manual_status(policy, snapshot, attestations, now=None):
    now = now or datetime.now(timezone.utc)
    checks = []
    for rule in manual_rules(policy):
        entry = attestations.get(rule["id"])
        status = "unverified"
        checked_at = None
        if isinstance(entry, dict):
            checked_at = entry.get("checked_at")
            try:
                checked = datetime.fromisoformat(checked_at)
                fresh = timedelta(0) <= now - checked <= timedelta(days=policy.get("manual_review_days", 30))
            except (ValueError, TypeError):
                fresh = False
            matches = entry.get("policy_hash") == digest(policy) and entry.get("device") == identity(snapshot)
            if not matches or not fresh:
                status = "stale"
            elif entry.get("result") == "pass":
                status = "self-reported-pass"
            elif entry.get("result") == "fail":
                status = "self-reported-fail"
        checks.append({**rule, "status": status, "checked_at": checked_at})
    return checks
