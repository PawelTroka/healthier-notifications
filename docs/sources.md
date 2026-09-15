# Sources and capability boundaries

Reviewed **2026-09-15**. These are primary documentation or source-code references. AOSP behavior is a baseline; commands and parsing must still be checked against the connected ColorOS build. Product pages establish that models exist, not which device the user owns.

## Android

| Source | What it supports |
| --- | --- |
| [Android Debug Bridge](https://developer.android.com/tools/adb) | USB debugging setup, computer-key authorization, `devices -l`, explicit `-s SERIAL` targeting, and shell commands. |
| [SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) | Official portable ADB downloads. This working copy was prepared with version 37.0.1-15733141 for Windows. |
| [Notification runtime permission](https://developer.android.com/develop/ui/compose/notifications/notification-permission) | Android 13/API 33+ `POST_NOTIFICATIONS`; documented ADB grant/revoke examples; whole-app non-exempt notification blocking and exceptions. |
| [Create and manage notification channels](https://developer.android.com/develop/ui/compose/notifications/channels) | User control of channel sound/importance; channel settings intent; individual categories are separate from the whole-app permission. |
| [AOSP PackageManagerShellCommand](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/pm/PackageManagerShellCommand.java) | `grant/revoke --user USER_ID PACKAGE PERMISSION` and permission-flag syntax. No `pm check-permission` command in the reviewed implementation. |
| [AOSP Android 16 notification shell commands](https://android.googlesource.com/platform/frameworks/base/+/android16-qpr2-release/services/core/java/com/android/server/notification/NotificationShellCmd.java) | `cmd notification` exposes selected DND, listener, bubble, test-post and snooze operations; its reviewed help has no general arbitrary channel-importance setter. |
| [AOSP AppOpsService](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/services/core/java/com/android/server/appop/AppOpsService.java) | `appops get/set --user` syntax and the distinction between app-op modes and runtime permissions. |

Supported whole-app command shape for the tool's reviewed, non-system Android 13+ rules:

```text
adb -s SERIAL shell pm revoke --user USER_ID PACKAGE android.permission.POST_NOTIFICATIONS
adb -s SERIAL shell pm grant --user USER_ID PACKAGE android.permission.POST_NOTIFICATIONS
```

The script preserves permission flags. Android's developer page also lists flag-changing commands for simulating fresh installs and upgrade flows; those are testing recipes, not a reason to reset an existing user's permission history. The project does not mix raw `POST_NOTIFICATION` app-op changes with runtime-permission changes. A successful process exit must be followed by measured-state verification.

Permission state can be inspected in `dumpsys package PACKAGE`; parsing must select the correct user's runtime-permission block. A permission declaration alone is not a grant, and a grant alone is not proof that every notification channel can alert. Unknown or changed output must not be interpreted as an enabled or disabled permission.

## OPPO

| Source | What it supports |
| --- | --- |
| [Find X9 Ultra specifications](https://www.oppo.com/in/smartphones/series-find-x/find-x9-ultra/specs/) | Published Find X9 Ultra model CPH2841 and ColorOS 16.0 for this market; actual hardware/software must be inspected. |
| [Find X9 Ultra launch announcement](https://www.oppo.com/en/newsroom/press/oppo-find-x9-ultra-launch-camera/) | Model and ColorOS product context. It is not a verified menu-by-menu notification guide. |

ColorOS category names, DND exceptions, badge controls, and background-operation settings remain manual checks. This project does not claim that all regional Find X9 Ultra builds expose identical UI or ADB capabilities.

## Garmin

| Source | What it supports |
| --- | --- |
| [fēnix 9 product family](https://www.garmin.com/en-GB/p/2021175/pn/010-04763-01/) | fēnix 9/Pro family, optional inReach, and 43/47/51 mm case sizes. Keep the conversation's reported 52 mm detail unconfirmed. |
| [fēnix 9: Enabling Phone Notifications](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-043F879B-FC35-4B22-A025-DF91C157B13F.html) | Watch call/text/app alert controls, Android Garmin Connect app selection, blocked-app list, privacy and timeout. |
| [Garmin: Which notifications display?](https://support.garmin.com/en-IN/?faq=TLeDN92ZU0AgN4df6HakwA&identifier=780196&tab=topics) | General Android route: Garmin Connect > More > Settings > Notifications > App Notifications. Model-specific controls may differ. |
| [fēnix 9: Focus Modes](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-DF71C212-09EF-431B-87E9-40DEBD0C41A6.html) | Focus-specific settings for situations including sleep and activities. |
| [fēnix 9: Health and Wellness Alerts](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-EB335B47-6770-4A06-8EEC-8E0355507102.html) | Native daily summary, stress/rest, heart-rate, move and goal alert settings. |
| [fēnix 9: Phone Connection Alerts](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-1E446357-A244-44C2-BF72-DE150D68F292.html) | Bluetooth connection alerts under Notifications & Alerts > System Alerts > Phone. |
| [fēnix 9: Safety and Tracking Features](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-64F677A5-03E0-453F-BFE3-E1B93D6FA3FC.html) | Assistance, incident detection and tracking are separate functions with phone/LTE requirements depending on variant and plan. |
| [fēnix 9 Pro inReach feature requirements](https://www.garmin.com/en-US/connectivity/smartwatches/fenix-9-pro/feature-requirements/) | Separate inReach plan, LTE/satellite and Garmin Messenger requirements. |

No supported Garmin CLI or public API for reading/writing this personal watch's notification allowlist, native alerts, and focus settings was established in this review. The current project therefore records those settings as manual attestations. This is a project capability boundary, not proof that no other implementation is possible.

An installed app may expose **Follow Do Not Disturb Behavior**. This review did not find a primary Garmin support document establishing the current toggle's exact semantics. Inspect its presence and verify behavior on the actual phone, app version, and watch firmware. Do not claim automatic bidirectional DND synchronization or infer silent-channel behavior from the name.

## Microsoft Teams

| Source | What it supports |
| --- | --- |
| [Troubleshoot notifications in Teams mobile apps](https://support.microsoft.com/en-us/teams/notifications-settings/troubleshoot-notifications-in-microsoft-teams-mobile-apps) | Suppression while active on desktop/web, return after inactivity, separate meeting/in-app controls, and the exception that calls still notify mobile. |
| [Quiet time in Teams mobile](https://support.microsoft.com/en-us/teams/platform/quiet-time-in-microsoft-teams-for-mobile-devices) | Per-hour/day schedule, device-local time zones, optional Teams/Outlook schedule synchronization and Viva Insights sharing. Microsoft describes enabling that synchronization as irreversible. |

Teams rules, selected Garmin apps, ColorOS category choices, and quiet schedules are manual in this version. The tool's status report must distinguish measured Android permission state from these dated observations.
