"""ADB contract tests: all subprocesses are mocked; no device is contacted."""

import shlex
import subprocess
import unittest
from unittest.mock import patch

from healthier_notifications.android import AdbDevice, DeviceError, POST_NOTIFICATIONS, parse_package_dump


PACKAGE = "com.example.reader"


def package_dump(package=PACKAGE):
    return f"""Activity Resolver Table:
  unrelated: android.permission.POST_NOTIFICATIONS: granted=false

Packages:
  Package [{package}] (a1b2c3):
    userId=10123
    versionCode=42 minSdk=26 targetSdk=35
    requested permissions:
      android.permission.INTERNET
      android.permission.POST_NOTIFICATIONS
    install permissions:
      android.permission.POST_NOTIFICATIONS: granted=false
    User 0: ceDataInode=123 installed=true hidden=false suspended=false
      runtime permissions:
        android.permission.POST_NOTIFICATIONS: granted=true, flags=[ USER_SET|USER_SENSITIVE_WHEN_GRANTED ]
        android.permission.CAMERA: granted=false, flags=[]
    User 10: ceDataInode=456 installed=true hidden=false suspended=false
      runtime permissions:
        android.permission.POST_NOTIFICATIONS: granted=false, flags=[ USER_FIXED ]

Hidden system packages:
  Package [{package}] (d4e5f6):
    versionCode=1 minSdk=26 targetSdk=33
    User 0: installed=true
      runtime permissions:
        android.permission.POST_NOTIFICATIONS: granted=false, flags=[]
"""


def completed(output="", code=0, stderr=""):
    return subprocess.CompletedProcess([], code, output, stderr)


class PackageParserTests(unittest.TestCase):
    def test_reads_runtime_permission_for_exact_user_only(self):
        value = parse_package_dump(package_dump(), PACKAGE, 0)
        self.assertEqual(value, {
            "version_code": "42", "requests_notifications": True,
            "permission": {"granted": True, "flags": ["USER_SET", "USER_SENSITIVE_WHEN_GRANTED"]},
        })
        other_user = parse_package_dump(package_dump(), PACKAGE, 10)
        self.assertEqual(other_user["permission"], {"granted": False, "flags": ["USER_FIXED"]})

    def test_missing_user_never_borrows_another_user(self):
        for user in (1, 11, 100):
            with self.subTest(user=user):
                self.assertEqual(parse_package_dump(package_dump(), PACKAGE, user)["permission"],
                                 {"granted": None, "flags": []})

    def test_missing_runtime_row_is_unknown_not_denied(self):
        dump = package_dump().replace(
            "        android.permission.POST_NOTIFICATIONS: granted=true, flags=[ USER_SET|USER_SENSITIVE_WHEN_GRANTED ]\n", "")
        self.assertIsNone(parse_package_dump(dump, PACKAGE, 0)["permission"]["granted"])

    def test_uninstalled_user_is_unknown(self):
        dump = package_dump().replace("User 0: ceDataInode=123 installed=true", "User 0: ceDataInode=123 installed=false")
        self.assertIsNone(parse_package_dump(dump, PACKAGE, 0)["permission"]["granted"])

    def test_install_permission_is_never_runtime_permission(self):
        dump = package_dump().replace("      runtime permissions:", "      unrelated state:")
        self.assertIsNone(parse_package_dump(dump, PACKAGE, 0)["permission"]["granted"])

    def test_requested_permission_is_not_inferred_from_runtime_or_install(self):
        dump = package_dump().replace("      android.permission.POST_NOTIFICATIONS\n", "")
        self.assertFalse(parse_package_dump(dump, PACKAGE, 0)["requests_notifications"])

    def test_empty_flags_are_known_when_row_is_valid(self):
        dump = package_dump().replace("USER_SET|USER_SENSITIVE_WHEN_GRANTED", "")
        self.assertEqual(parse_package_dump(dump, PACKAGE, 0)["permission"], {"granted": True, "flags": []})

    def test_missing_flags_or_bad_state_are_unknown(self):
        for replacement in ("granted=yes, flags=[]", "granted=true", "granted=true, flags=[ USER FIXED ]"):
            with self.subTest(replacement=replacement):
                dump = package_dump().replace("granted=true, flags=[ USER_SET|USER_SENSITIVE_WHEN_GRANTED ]", replacement)
                self.assertIsNone(parse_package_dump(dump, PACKAGE, 0)["permission"]["granted"])

    def test_duplicate_runtime_rows_are_ambiguous(self):
        row = "        android.permission.POST_NOTIFICATIONS: granted=true, flags=[ USER_SET|USER_SENSITIVE_WHEN_GRANTED ]"
        dump = package_dump().replace(row, row + "\n" + row)
        self.assertIsNone(parse_package_dump(dump, PACKAGE, 0)["permission"]["granted"])

    def test_missing_package_or_unrecognized_layout_is_unknown(self):
        for dump in (package_dump("com.example.other"), "Unable to find package: " + PACKAGE,
                     package_dump().replace("Packages:", "Unexpected packages:")):
            with self.subTest(dump=dump[:30]):
                self.assertEqual(parse_package_dump(dump, PACKAGE, 0), {
                    "version_code": None, "requests_notifications": False,
                    "permission": {"granted": None, "flags": []},
                })

    def test_next_sibling_section_cannot_leak_a_grant(self):
        dump = package_dump().replace(
            "      runtime permissions:\n        android.permission.POST_NOTIFICATIONS: granted=true, flags=[ USER_SET|USER_SENSITIVE_WHEN_GRANTED ]",
            "      runtime permissions:\n        android.permission.CAMERA: granted=false, flags=[]\n"
            "      unrelated permissions:\n        android.permission.POST_NOTIFICATIONS: granted=true, flags=[]")
        self.assertIsNone(parse_package_dump(dump, PACKAGE, 0)["permission"]["granted"])


class SelectionAndProcessTests(unittest.TestCase):
    @patch("healthier_notifications.android.subprocess.run")
    def test_automatic_device_selection_and_current_user(self, run):
        run.side_effect = [completed("List of devices attached\nPHONE\tdevice product:phone model:Pixel"), completed("10")]
        device = AdbDevice()
        self.assertEqual(device._user(), 10)
        self.assertEqual(device.serial, "PHONE")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["adb", "-s", "PHONE", "shell", "am get-current-user"])
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["timeout"], 30)

    @patch("healthier_notifications.android.subprocess.run")
    def test_missing_multiple_unauthorized_offline_devices(self, run):
        cases = [
            ("", "No ADB device"),
            ("PHONE\tdevice\nWATCH\tdevice", "Multiple"),
            ("PHONE\tunauthorized", "unauthorized"),
            ("PHONE\toffline", "offline"),
            ("PHONE\trecovery", "recovery"),
            ("PHONE\tunauthorized\nWATCH\tdevice", "Multiple"),
        ]
        for listing, error in cases:
            with self.subTest(listing=listing):
                run.return_value = completed("List of devices attached\n" + listing)
                with self.assertRaisesRegex(DeviceError, error):
                    AdbDevice()._connect()

    @patch("healthier_notifications.android.subprocess.run")
    def test_explicit_serial_selects_only_that_device(self, run):
        run.return_value = completed("List of devices attached\nPHONE\tdevice\nWATCH\tdevice")
        device = AdbDevice(serial="PHONE", user=0)
        device._connect()
        self.assertEqual(device.serial, "PHONE")
        with self.assertRaisesRegex(DeviceError, "not uniquely present"):
            AdbDevice(serial="MISSING")._connect()

    @patch("healthier_notifications.android.subprocess.run")
    def test_missing_adb_and_timeout_are_actionable(self, run):
        run.side_effect = FileNotFoundError("adb")
        with self.assertRaisesRegex(DeviceError, "Platform-Tools"):
            AdbDevice().devices()
        run.side_effect = subprocess.TimeoutExpired("adb", 30)
        with self.assertRaisesRegex(DeviceError, "capture state again"):
            AdbDevice().devices()

    @patch("healthier_notifications.android.subprocess.run")
    def test_nonzero_and_zero_exit_error_messages_raise(self, run):
        for result in (completed("", 1, "device disconnected"),
                       completed("Error: unknown option"),
                       completed("java.lang.SecurityException: Permission is policy fixed"),
                       completed("Permission denied")):
            with self.subTest(result=result):
                run.return_value = result
                with self.assertRaises(DeviceError):
                    AdbDevice().version()

    @patch("healthier_notifications.android.subprocess.run")
    def test_user_and_package_rejected_before_any_command(self, run):
        for user in (-1, True, "0", "all", "current"):
            with self.subTest(user=user), self.assertRaises(DeviceError):
                AdbDevice(user=user)
        for package in ("com.example;reboot", "com.example app", "$(reboot)", "--help", "", "a\0b"):
            with self.subTest(package=package), self.assertRaises(DeviceError):
                AdbDevice().set_permission(package, False)
        run.assert_not_called()

    @patch("healthier_notifications.android.subprocess.run")
    def test_unrecognized_user_is_not_guessed(self, run):
        run.side_effect = [completed("List of devices attached\nPHONE\tdevice"), completed("Current user unknown")]
        with self.assertRaisesRegex(DeviceError, "Could not determine"):
            AdbDevice()._user()


class PermissionAndSettingsTests(unittest.TestCase):
    @patch("healthier_notifications.android.subprocess.run")
    def test_permission_command_targets_exact_serial_user_permission(self, run):
        for granted, operation in ((False, "revoke"), (True, "grant")):
            with self.subTest(granted=granted):
                run.reset_mock()
                run.side_effect = [completed("List of devices attached\nPHONE\tdevice"), completed("35"), completed()]
                AdbDevice(serial="PHONE", user=10).set_permission(PACKAGE, granted)
                self.assertEqual(run.call_args.args[0], ["adb", "-s", "PHONE", "shell",
                    f"pm {operation} --user 10 {PACKAGE} {POST_NOTIFICATIONS}"])
                self.assertFalse(run.call_args.kwargs["shell"])
                self.assertEqual(run.call_count, 3)

    @patch("healthier_notifications.android.subprocess.run")
    def test_pre_android_13_never_sends_permission_mutation(self, run):
        run.side_effect = [completed("List of devices attached\nPHONE\tdevice"), completed("32")]
        with self.assertRaisesRegex(DeviceError, "Android 13"):
            AdbDevice(user=0).set_permission(PACKAGE, False)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(any("pm revoke" in str(call) for call in run.call_args_list))

    @patch("healthier_notifications.android.subprocess.run")
    def test_permission_failure_propagates(self, run):
        run.side_effect = [completed("List of devices attached\nPHONE\tdevice"), completed("35"),
                           completed("", 1, "java.lang.SecurityException: Permission is fixed")]
        with self.assertRaisesRegex(DeviceError, "Permission is fixed"):
            AdbDevice(user=0).set_permission(PACKAGE, False)

    @patch("healthier_notifications.android.subprocess.run")
    def test_settings_intents_clear_previous_page_for_requested_user(self, run):
        cases = [
            (None, None, "android.settings.NOTIFICATION_SETTINGS", []),
            (PACKAGE, None, "android.settings.APP_NOTIFICATION_SETTINGS",
             ["--es", "android.provider.extra.APP_PACKAGE", PACKAGE]),
            (PACKAGE, "direct_messages", "android.settings.CHANNEL_NOTIFICATION_SETTINGS",
             ["--es", "android.provider.extra.APP_PACKAGE", PACKAGE,
              "--es", "android.provider.extra.CHANNEL_ID", "direct_messages"]),
        ]
        for package, channel, action, extras in cases:
            with self.subTest(package=package, channel=channel):
                run.reset_mock()
                run.side_effect = [completed("List of devices attached\nPHONE\tdevice"),
                                   completed("Starting: Intent")]
                self.assertEqual(AdbDevice(user=10).open_settings(package, channel), "Starting: Intent")
                self.assertEqual(shlex.split(run.call_args.args[0][4]),
                                 ["am", "start", "--user", "10", "-f", "0x10008000",
                                  "-a", action, *extras])
                self.assertEqual(run.call_count, 2)

    @patch("healthier_notifications.android.subprocess.run")
    def test_remote_channel_is_single_quoted_argument(self, run):
        run.side_effect = [completed("List of devices attached\nPHONE\tdevice"), completed("Starting: Intent")]
        channel = "news and 'updates'; $(reboot); `reboot`\nwith newline"
        AdbDevice(adb=r"C:\Android Tools\adb.exe", user=10).open_settings(PACKAGE, channel)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:4], [r"C:\Android Tools\adb.exe", "-s", "PHONE", "shell"])
        self.assertEqual(len(argv), 5)
        self.assertEqual(shlex.split(argv[4]), ["am", "start", "--user", "10", "-f", "0x10008000", "-a",
            "android.settings.CHANNEL_NOTIFICATION_SETTINGS", "--es", "android.provider.extra.APP_PACKAGE",
            PACKAGE, "--es", "android.provider.extra.CHANNEL_ID", channel])
        self.assertFalse(run.call_args.kwargs["shell"])

    @patch("healthier_notifications.android.subprocess.run")
    def test_settings_missing_activity_has_manual_instruction(self, run):
        run.side_effect = [completed("List of devices attached\nPHONE\tdevice"),
                           completed("Error: Activity not started, unable to resolve Intent")]
        with self.assertRaisesRegex(DeviceError, "Settings > Notifications"):
            AdbDevice(user=0).open_settings(PACKAGE)


class SnapshotTests(unittest.TestCase):
    def responder(self, command, **kwargs):
        self.commands.append(command)
        if command[1:] == ["devices", "-l"]:
            return completed("List of devices attached\nPHONE\tdevice")
        args = shlex.split(command[4])
        if args[:1] == ["getprop"]:
            return completed({"ro.build.version.sdk": str(self.sdk), "ro.product.manufacturer": "Google",
                "ro.product.model": "Pixel", "ro.build.version.release": "15",
                "ro.build.fingerprint": "google/test/test:15/BUILD/123:user/release-keys"}[args[1]])
        if args == ["pm", "list", "packages", "-U", "--user", "10"]:
            return completed(f"package:android uid:1001000\npackage:{PACKAGE} uid:1010123\n"
                "package:com.example.dialer uid:1010124\npackage:com.garmin.android.apps.connectmobile uid:1010125")
        if args == ["pm", "list", "packages", "-s", "--user", "10"]:
            return completed("package:android")
        if args[:3] == ["cmd", "role", "get-role-holders"]:
            if self.roles_fail:
                return completed("Unknown command: get-role-holders", 1)
            return completed("com.example.dialer" if args[-1].endswith("DIALER") else "")
        if args[:2] == ["dumpsys", "package"]:
            return completed(package_dump(args[2]))
        raise AssertionError(f"Unexpected mock ADB command: {command}")

    def setUp(self):
        self.commands = []
        self.sdk = 35
        self.roles_fail = False
        patcher = patch("healthier_notifications.android.subprocess.run", side_effect=self.responder)
        self.run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_snapshot_shape_user_flags_protection_and_absent_packages(self):
        snapshot = AdbDevice(user=10).snapshot([PACKAGE, "com.example.dialer", "com.example.absent",
                                               "com.garmin.android.apps.connectmobile"])
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertTrue(snapshot["captured_at"].endswith("+00:00"))
        self.assertEqual(snapshot["device"]["user"], 10)
        self.assertTrue(snapshot["device"]["roles_verified"])
        app = snapshot["packages"][PACKAGE]
        self.assertEqual(app["uid"], 1010123)
        self.assertFalse(app["system"])
        self.assertFalse(app["shared_uid"])
        self.assertEqual(app["permission"], {"granted": False, "flags": ["USER_FIXED"]})
        self.assertTrue(snapshot["packages"]["com.example.dialer"]["protected"])
        self.assertTrue(snapshot["packages"]["com.garmin.android.apps.connectmobile"]["protected"])
        self.assertNotIn("com.example.absent", snapshot["packages"])
        self.assertEqual(snapshot["inspected_packages"],
                         sorted([PACKAGE, "com.example.dialer", "com.garmin.android.apps.connectmobile"]))
        self.assertTrue(any("not installed" in warning for warning in snapshot["warnings"]))
        self.assertFalse(any("dumpsys notification" in str(command) for command in self.commands))

    def test_no_package_filter_inventories_all_packages(self):
        snapshot = AdbDevice(user=10).snapshot()
        self.assertEqual(len(snapshot["packages"]), 4)
        self.assertTrue(snapshot["packages"]["android"]["system"])
        self.assertTrue(snapshot["packages"]["android"]["protected"])
        self.assertEqual(snapshot["inspected_packages"], sorted(snapshot["packages"]))

    def test_subset_keeps_all_installed_packages_but_inspects_only_subset(self):
        snapshot = AdbDevice(user=10).snapshot([PACKAGE])
        self.assertEqual(len(snapshot["packages"]), 4)
        self.assertEqual(snapshot["inspected_packages"], [PACKAGE])
        dialer = snapshot["packages"]["com.example.dialer"]
        self.assertEqual(dialer, {"uid": 1010124, "system": False, "shared_uid": False,
            "version_code": None, "requests_notifications": False,
            "permission": {"granted": None, "flags": []}, "protected": True})
        self.assertEqual([shlex.split(command[4])[-1] for command in self.commands
                          if len(command) == 5 and command[4].startswith("dumpsys package")], [PACKAGE])

    def test_empty_subset_is_inventory_only(self):
        snapshot = AdbDevice(user=10).snapshot([])
        self.assertEqual(len(snapshot["packages"]), 4)
        self.assertEqual(snapshot["inspected_packages"], [])
        self.assertTrue(all(app["permission"]["granted"] is None for app in snapshot["packages"].values()))
        self.assertFalse(any("dumpsys package" in str(command) for command in self.commands))

    def test_uid_sharing_protects_inspected_and_uninspected_siblings(self):
        original = self.responder
        def response(command, **kwargs):
            if "pm list packages -U" in str(command):
                return completed(f"package:android uid:1001000\npackage:{PACKAGE} uid:1010123\n"
                                 "package:com.example.sibling uid:1010123\n"
                                 "package:com.example.systemsibling uid:1001000\n"
                                 "package:com.example.unique uid:1010124")
            return original(command, **kwargs)
        self.run.side_effect = response
        snapshot = AdbDevice(user=10).snapshot([PACKAGE])
        self.assertEqual(snapshot["inspected_packages"], [PACKAGE])
        for package in ("android", PACKAGE, "com.example.sibling", "com.example.systemsibling"):
            with self.subTest(package=package):
                self.assertTrue(snapshot["packages"][package]["shared_uid"])
                self.assertTrue(snapshot["packages"][package]["protected"])
        self.assertFalse(snapshot["packages"]["com.example.unique"]["shared_uid"])
        self.assertFalse(snapshot["packages"]["com.example.unique"]["protected"])
        self.assertIsNone(snapshot["packages"]["com.example.sibling"]["permission"]["granted"])

    def test_role_failure_marks_protection_unverified(self):
        self.roles_fail = True
        snapshot = AdbDevice(user=10).snapshot([PACKAGE])
        self.assertFalse(snapshot["device"]["roles_verified"])
        self.assertEqual(len(snapshot["warnings"]), 2)

    def test_sdk_below_33_snapshot_is_read_only_unknown(self):
        self.sdk = 32
        snapshot = AdbDevice(user=10).snapshot([PACKAGE])
        self.assertEqual(snapshot["packages"][PACKAGE]["permission"], {"granted": None, "flags": []})
        self.assertIn("below 33", snapshot["warnings"][0])

    def test_bad_or_empty_system_inventory_fails_closed(self):
        original = self.responder
        for output in ("", "package:com.not.in.inventory"):
            def response(command, **kwargs):
                if "pm list packages -s" in str(command):
                    return completed(output)
                return original(command, **kwargs)
            self.run.side_effect = response
            with self.subTest(output=output), self.assertRaisesRegex(DeviceError, "inventory"):
                AdbDevice(user=10).snapshot([PACKAGE])

    def test_missing_uid_is_not_inferred(self):
        with self.assertRaisesRegex(DeviceError, "UIDs"):
            AdbDevice._parse_packages("package:com.example.app", True)


if __name__ == "__main__":
    unittest.main()
