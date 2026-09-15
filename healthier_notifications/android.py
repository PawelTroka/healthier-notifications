"""Small, conservative ADB adapter for notification permission snapshots.

No notification content is collected. Android's package dump is an implementation
detail, so unfamiliar or ambiguous permission layouts produce an unknown state.
Only POST_NOTIFICATIONS may be changed; callers supply the policy and review.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
import shlex
import subprocess
from typing import Iterable


POST_NOTIFICATIONS = "android.permission.POST_NOTIFICATIONS"
PACKAGE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
PROTECTED_PACKAGES = frozenset({
    "android", "com.android.systemui", "com.android.settings",
    "com.android.phone", "com.android.server.telecom", "com.android.dialer",
    "com.android.mms", "com.android.messaging", "com.android.providers.telephony",
    "com.android.deskclock", "com.android.alarmclock",
    "com.android.cellbroadcastreceiver", "com.android.cellbroadcastservice",
    "com.google.android.dialer", "com.google.android.apps.messaging",
    "com.google.android.deskclock", "com.google.android.cellbroadcastreceiver",
    "com.google.android.cellbroadcastservice", "com.samsung.android.dialer",
    "com.samsung.android.messaging", "com.sec.android.app.clockpackage",
    "com.samsung.android.incallui", "com.garmin.android.apps.connectmobile",
    "com.garmin.android.apps.messenger",
})
_COMMAND_ERROR = re.compile(
    r"(?im)^\s*(?:error:|failure\b|exception(?: occurred)?\b|"
    r"java\.[\w.]*Exception\b|security exception:|unknown command:|unknown option:|"
    r"can't find service:|cmd: can't find service:|permission denial:|permission denied|"
    r"unknown package:|operation not allowed:)"
)


class DeviceError(Exception):
    """ADB failed, the device is ambiguous, or safe state cannot be established."""


def validate_package(package: str) -> str:
    if not isinstance(package, str) or not PACKAGE_RE.fullmatch(package):
        raise DeviceError(f"Invalid Android package name: {package!r}")
    return package


def _validate_user(user: int) -> int:
    if type(user) is not int or user < 0:
        raise DeviceError("Android user must be an explicit nonnegative integer.")
    return user


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _children(lines: list[str], index: int) -> list[str]:
    """Return only the indented body of a heading, never a sibling section."""
    depth = _indent(lines[index])
    result = []
    for line in lines[index + 1:]:
        if line.strip() and _indent(line) <= depth:
            break
        result.append(line)
    return result


def parse_package_dump(text: str, package: str, user: int) -> dict:
    """Extract a package's requested permission and exact user's runtime state.

    Never infer a grant from install permissions, another user, an absent row,
    or a shared/hidden package section. A missing row is unknown, not denied.
    """
    validate_package(package)
    _validate_user(user)
    result = {
        "version_code": None,
        "requests_notifications": False,
        "permission": {"granted": None, "flags": []},
    }
    lines = text.expandtabs(8).splitlines()
    sections = [i for i, line in enumerate(lines) if line.strip() == "Packages:"]
    if len(sections) != 1:
        return result
    packages = _children(lines, sections[0])
    heading = re.compile(r"\s*Package \[" + re.escape(package) + r"\] \([^\n]*\):\s*")
    matches = [i for i, line in enumerate(packages) if heading.fullmatch(line)]
    if len(matches) != 1:
        return result
    body = _children(packages, matches[0])
    versions = [re.match(r"\s*versionCode=(\d+)(?:\s|$)", line) for line in body]
    values = [match.group(1) for match in versions if match]
    if len(values) == 1:
        result["version_code"] = values[0]
    requested = [i for i, line in enumerate(body) if line.strip() == "requested permissions:"]
    if len(requested) == 1:
        result["requests_notifications"] = any(
            line.strip() == POST_NOTIFICATIONS for line in _children(body, requested[0])
        )
    user_heading = re.compile(r"\s*User " + str(user) + r":(?:\s.*)?")
    users = [i for i, line in enumerate(body) if user_heading.fullmatch(line)]
    if len(users) != 1:
        return result
    if re.search(r"\binstalled=false\b", body[users[0]]):
        return result
    user_body = _children(body, users[0])
    runtime = [i for i, line in enumerate(user_body) if line.strip() == "runtime permissions:"]
    if len(runtime) != 1:
        return result
    rows = [line.strip() for line in _children(user_body, runtime[0])
            if line.strip().startswith(POST_NOTIFICATIONS + ":")]
    if len(rows) != 1:
        return result
    grant = re.fullmatch(
        re.escape(POST_NOTIFICATIONS) + r":\s*granted=(true|false),\s*flags=\[([^\]]*)\]\s*",
        rows[0],
    )
    if not grant:
        return result
    raw_flags = grant.group(2).strip()
    flags = [flag.strip() for flag in raw_flags.split("|")] if raw_flags else []
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*|0x[0-9a-fA-F]+", flag) for flag in flags):
        return result
    result["permission"] = {"granted": grant.group(1) == "true", "flags": flags}
    return result


class AdbDevice:
    """Lazily select one authorized ADB device, pinning serial and Android user."""

    def __init__(self, adb: str = "adb", serial: str | None = None, user: int | None = None):
        if not isinstance(adb, str) or not adb or "\0" in adb:
            raise DeviceError("ADB must be an executable name or path.")
        if serial is not None and (
            not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", serial)
        ):
            raise DeviceError("Invalid ADB serial. Use a serial printed by 'adb devices'.")
        if user is not None:
            _validate_user(user)
        self.adb = adb
        self.serial = serial
        self.user = user
        self.timeout = 30
        self._connected = False

    def _run(self, args: list[str]) -> str:
        command = [self.adb, *args]
        options = {
            "capture_output": True, "text": True, "encoding": "utf-8",
            "errors": "replace", "timeout": self.timeout, "shell": False,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            completed = subprocess.run(command, **options)
        except FileNotFoundError as exc:
            raise DeviceError(
                "ADB was not found. Install Android SDK Platform-Tools and add it to PATH, "
                "or pass --adb with the adb executable path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DeviceError(
                f"ADB timed out after {self.timeout}s. Check the USB connection and unlocked phone. "
                "If a permission command timed out, capture state again before retrying."
            ) from exc
        except OSError as exc:
            raise DeviceError(f"Could not run ADB: {exc}") from exc
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode != 0 or _COMMAND_ERROR.search(stdout) or _COMMAND_ERROR.search(stderr):
            detail = (stderr.strip() or stdout.strip() or "no error details")[:1800]
            raise DeviceError(f"ADB command failed (exit {completed.returncode}): {detail}")
        return stdout.strip()

    def version(self) -> str:
        return self._run(["version"])

    def devices(self) -> list[dict[str, str]]:
        output = self._run(["devices", "-l"])
        lines = output.splitlines()
        if not any(line.strip() == "List of devices attached" for line in lines):
            raise DeviceError("Unexpected 'adb devices' output; update Android SDK Platform-Tools.")
        result = []
        for line in lines:
            line = line.strip()
            if not line or line == "List of devices attached" or line.startswith("* daemon"):
                continue
            parts = line.split()
            if len(parts) < 2:
                raise DeviceError("Unrecognized ADB device listing; inspect 'adb devices -l'.")
            result.append({"serial": parts[0], "state": parts[1]})
        return result

    def _connect(self) -> None:
        if self._connected:
            return
        devices = self.devices()
        if self.serial is None:
            if not devices:
                raise DeviceError("No ADB device found. Connect the phone, enable USB debugging, and approve its RSA prompt.")
            if len(devices) != 1:
                raise DeviceError("Multiple ADB devices are connected. Choose the phone explicitly with --serial.")
            selected = devices[0]
        else:
            candidates = [device for device in devices if device["serial"] == self.serial]
            if len(candidates) != 1:
                raise DeviceError(f"ADB device {self.serial!r} is not uniquely present. Inspect 'adb devices -l'.")
            selected = candidates[0]
        if selected["state"] == "unauthorized":
            raise DeviceError("Phone is unauthorized. Unlock it and approve the USB debugging RSA prompt.")
        if selected["state"] != "device":
            raise DeviceError(f"ADB device is {selected['state']!r}, not ready. Reconnect it and inspect 'adb devices -l'.")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", selected["serial"]):
            raise DeviceError("ADB returned an unsupported device serial format.")
        self.serial = selected["serial"]
        self._connected = True

    def _shell(self, *args: str) -> str:
        self._connect()
        if any(not isinstance(arg, str) or "\0" in arg for arg in args):
            raise DeviceError("Android shell arguments must be strings without NUL characters.")
        # adb shell has a second, remote shell parsing step. Host argv alone is
        # insufficient: channel IDs may legitimately contain spaces or quotes.
        remote_command = " ".join(shlex.quote(arg) for arg in args)
        return self._run(["-s", self.serial, "shell", remote_command])

    def _user(self) -> int:
        if self.user is None:
            value = self._shell("am", "get-current-user")
            if not re.fullmatch(r"\d+", value):
                raise DeviceError("Could not determine the Android user. Pass --user with a numeric user ID.")
            self.user = int(value)
        return _validate_user(self.user)

    def _sdk(self) -> int:
        value = self._shell("getprop", "ro.build.version.sdk")
        if not re.fullmatch(r"\d+", value):
            raise DeviceError("Could not read the Android SDK version; permission changes are unavailable.")
        return int(value)

    @staticmethod
    def _parse_packages(output: str, require_uid: bool) -> dict[str, int | None]:
        packages = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(r"package:([^\s]+)(?:\s+uid:(\d+))?", line.strip())
            if not match:
                raise DeviceError("Unexpected package listing; refusing to infer installed apps.")
            package = validate_package(match.group(1))
            if package in packages:
                raise DeviceError(f"Ambiguous package listing for {package}.")
            if require_uid and match.group(2) is None:
                raise DeviceError("Package manager did not return UIDs; update Platform-Tools or use manual settings.")
            packages[package] = int(match.group(2)) if match.group(2) is not None else None
        return packages

    def snapshot(self, packages: Iterable[str] | None = None) -> dict:
        """Inventory every installed app, inspecting permissions for selected apps.

        An explicit subset limits expensive package dumps only. Uninspected apps
        remain in the inventory with unknown permission/version metadata, making
        newly installed apps and UID-sharing siblings visible to the caller.
        """
        if isinstance(packages, (str, bytes)):
            raise DeviceError("packages must be a collection of package names, not one string.")
        requested = None if packages is None else sorted({validate_package(package) for package in packages})
        user = self._user()
        sdk = self._sdk()
        metadata = {"serial": self.serial, "user": user, "sdk": sdk}
        for key, prop in (("manufacturer", "ro.product.manufacturer"), ("model", "ro.product.model"),
                          ("android", "ro.build.version.release"), ("fingerprint", "ro.build.fingerprint")):
            metadata[key] = self._shell("getprop", prop)
        if not metadata["fingerprint"]:
            raise DeviceError("Device did not report its build fingerprint; a trustworthy snapshot is unavailable.")
        installed = self._parse_packages(self._shell("pm", "list", "packages", "-U", "--user", str(user)), True)
        systems = self._parse_packages(self._shell("pm", "list", "packages", "-s", "--user", str(user)), False)
        if not systems or not set(systems).issubset(installed):
            raise DeviceError("System package inventory is empty or inconsistent. Capture again before planning changes.")
        warnings = []
        protected = set(PROTECTED_PACKAGES)
        metadata["roles_verified"] = True
        for role in ("android.app.role.DIALER", "android.app.role.SMS"):
            try:
                holders = self._shell("cmd", "role", "get-role-holders", "--user", str(user), role)
                for holder in re.split(r"[;\r\n]+", holders):
                    if holder.strip():
                        protected.add(validate_package(holder.strip()))
            except DeviceError as exc:
                metadata["roles_verified"] = False
                warnings.append(f"Could not determine protected role {role}: {exc}")
        if sdk < 33:
            warnings.append("Android SDK is below 33; POST_NOTIFICATIONS changes are unsupported. Use phone settings.")
        uid_counts = Counter(installed.values())
        result = {}
        for package in sorted(installed):
            shared_uid = uid_counts[installed[package]] > 1
            result[package] = {
                "uid": installed[package], "system": package in systems,
                "shared_uid": shared_uid, "version_code": None,
                "requests_notifications": False,
                "permission": {"granted": None, "flags": []},
                "protected": package in protected or shared_uid,
            }
        inspected = []
        for package in (sorted(installed) if requested is None else requested):
            if package not in installed:
                warnings.append(f"{package} is not installed for Android user {user}.")
                continue
            parsed = parse_package_dump(self._shell("dumpsys", "package", package), package, user)
            if sdk < 33:
                parsed["permission"] = {"granted": None, "flags": []}
            result[package].update(parsed)
            inspected.append(package)
            if (sdk >= 33 and parsed["permission"]["granted"] is None
                    and (parsed["requests_notifications"] or parsed["version_code"] is None)):
                warnings.append(f"{package}: notification runtime permission is unknown for Android user {user}; manual review only.")
        return {"schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
                "device": metadata, "packages": result, "inspected_packages": inspected,
                "warnings": warnings}

    def set_permission(self, package: str, granted: bool) -> None:
        """Change only the notification grant; never clear or rewrite flags."""
        validate_package(package)
        if type(granted) is not bool:
            raise DeviceError("granted must be true or false.")
        if self._sdk() < 33:
            raise DeviceError("Notification permission changes require Android 13 (SDK 33) or later. Use phone settings.")
        user = self._user()
        self._shell("pm", "grant" if granted else "revoke", "--user", str(user), package, POST_NOTIFICATIONS)

    def open_settings(self, package: str | None = None, channel: str | None = None) -> str:
        """Open Android settings for manual review; return the activity output."""
        if package is not None:
            validate_package(package)
        if channel is not None and (package is None or not isinstance(channel, str) or not channel or "\0" in channel):
            raise DeviceError("A channel ID requires a package and must be a nonempty string without NUL characters.")
        if package is None:
            action = "android.settings.NOTIFICATION_SETTINGS"
            extras = []
        elif channel is None:
            action = "android.settings.APP_NOTIFICATION_SETTINGS"
            extras = ["--es", "android.provider.extra.APP_PACKAGE", package]
        else:
            action = "android.settings.CHANNEL_NOTIFICATION_SETTINGS"
            extras = ["--es", "android.provider.extra.APP_PACKAGE", package,
                      "--es", "android.provider.extra.CHANNEL_ID", channel]
        try:
            return self._shell("am", "start", "--user", str(self._user()), "-a", action, *extras)
        except DeviceError as exc:
            raise DeviceError(
                f"Could not open this Android settings page: {exc} "
                "Open Settings > Notifications on the phone and select the app manually."
            ) from exc
