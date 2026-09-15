# Phone and watch notification setup

Use the repository to describe the interruptions you want, apply the small part Android exposes reliably, and record the settings that need a manual check. Start with the launcher and connection instructions in the [README](../README.md). The source register is in [sources.md](sources.md).

## Confirm the devices first

The referenced conversation reports an **OPPO Find X9 Ultra** and a **Garmin Fenix 9 Pro inReach, 52 mm**. These are reported details, not an inventory from connected hardware. OPPO publishes Find X9 Ultra specifications with ColorOS 16. Garmin publishes fēnix 9 Pro models with inReach, and lists the large case as **51 mm**. Record the actual phone model, Android version, watch variant, firmware, and Garmin Connect version when setting up. Regional software and later updates can change menu labels. [OPPO specifications](https://www.oppo.com/in/smartphones/series-find-x/find-x9-ultra/specs/), [Garmin product family](https://www.garmin.com/en-GB/p/2021175/pn/010-04763-01/).

Connect the unlocked phone by USB, enable USB debugging, and accept the computer's debugging key on the phone. `adb devices -l` should show the intended device as `device`; `unauthorized` needs the on-phone prompt. Select the intended serial explicitly when more than one device is connected. [Android ADB instructions](https://developer.android.com/tools/adb).

Run `init` to discover installed apps and create a draft with their notification permissions preserved. Review real package names before changing any app rule. Keep device serials, installed-app inventories, and raw local snapshots in the ignored `.local` directory.

## Decide what deserves an interruption

This is a starting point for review, not an automatically applied policy:

| Notification type | Phone | Watch |
| --- | --- | --- |
| Personal direct messages from every communicator app | Keep direct-message notifications; remove unrelated social/promotional categories | Allow the communicator apps; filter unwanted categories at their source |
| Clock and wake-up alarms | Always preserve; weekday wake-up at 10:09 Warsaw time, including during quiet hours | Preserve deliberately configured native watch alarms; test separately |
| Calendar reminders and genuinely time-sensitive tasks | Keep selected reminders | Allow only those useful away from the phone |
| Work direct messages, Teams chat and mentions | Keep useful work messages during Monday-Friday 10:14-18:14 Europe/Warsaw; suppress desktop duplicates | Follow the same work boundary using app quiet hours and verified watch behavior |
| Email, news, social reactions, shopping promotions | Silence or turn off the unnecessary categories | Usually exclude from the app allowlist |
| Garmin goal celebrations, stress/rest summaries, move reminders | Review each type | Keep useful prompts; remove the repetitive ones |
| Alarms, navigation, security, abnormal-heart-rate, assistance and inReach messages | Preserve during initial cleanup | Preserve during initial cleanup |

Three different decisions matter: **whether a notification exists**, **whether the phone alerts**, and **whether the watch receives it**. A phone notification can remain available silently while its app is excluded from the Garmin watch. Blocking an app's Android notification permission is broader: it blocks that app's ordinary notifications across its categories. Android documents exceptions, including certain media and self-managed-call notifications, so this is not a promise to suppress every possible alert. [Android notification permission](https://developer.android.com/develop/ui/compose/notifications/notification-permission).

## Android and ColorOS: use app categories for fine control

For apps you still need, open their notification settings and review their categories, also called channels. Keep direct messages or delivery updates while silencing promotional categories when the app exposes them. Choose sound, vibration, banners, lock-screen visibility, and badges according to what the actual ColorOS screen offers. Also review settings inside the app, where categories or account-specific controls may be more precise. Android channel settings belong to the user after creation. [Android notification channels](https://developer.android.com/develop/ui/compose/notifications/channels).

`open-settings --package PACKAGE` opens an app's notification settings. Add `--channel CHANNEL_ID` only when you know the real channel ID. Labels shown in the UI are not necessarily channel IDs, and apps can create new channels later.

The automated backend is deliberately narrow: on supported Android versions, reviewed non-system package rules can grant or revoke `android.permission.POST_NOTIFICATIONS`. It does not clear permission flags, change channel importance, set conversation priorities, rewrite DND schedules, or modify private app settings. A grant does not prove the app's individual channels are enabled or that Garmin will mirror them. A revoke is a whole-app decision, so use manual category controls when you want some notifications from that app.

The work window is **Monday-Friday, 10:14-18:14, Europe/Warsaw**, as requested. Preserve those exact minute values. Personal direct messages from all communicator apps remain separate from this work schedule. No sleep schedule has been chosen. Before using phone-wide DND, review wanted exceptions so a work quiet period does not accidentally silence personal direct messages. Verify an ordinary alarm and a wanted call with the chosen settings. Phone DND, silent channels, Teams quiet time, and watch focus settings are separate controls.

## Wake-up alarm: 10:09 on weekdays

The user's chosen wake-up time is **10:09 Monday-Friday, Europe/Warsaw**, to be at the desk by **10:14**. This alarm is an explicit exception to work quiet hours and sleep/DND. Preserve other deliberately configured clock alarms too.

Configure the recurring alarm in the actual Clock app when the phone is connected. Check its selected weekdays, enabled state, sound and alarm volume; allow alarms in the phone's quiet-mode settings. Preserve the clock app's notification permission. If it is a third-party app, classify it as `reminders` with `phone: "preserve"` so whole-app blocking is rejected.

Create a short test alarm while the phone is locked, DND/sleep is active, work notifications are quiet and the watch is disconnected. Confirm the phone alarm actually sounds. If a native Garmin alarm is also part of the wake-up setup, test it independently during Sleep Focus. An app-allowlist check does not establish whether an alarm will wake you.

Remove the temporary test alarm afterward and leave the weekday 10:09 alarm enabled. Record `test.wake_alarm` as passed only after the recurring configuration and practical test are verified. The repository stores this desired alarm; its commands do not create the real device alarm automatically. Recheck the intended Warsaw time when travelling.

## Teams: reduce duplicate and out-of-hours alerts

In Teams mobile, open your profile picture, then **Notifications**. Under the blocking options, enable **When active on other devices** if you want messages to stop interrupting the phone while you use Teams on desktop or the web. Microsoft says mobile notifications resume after several minutes of inactivity; **calls can still notify the phone while desktop is active**. Review in-meeting and in-app notifications separately. [Teams mobile notification help](https://support.microsoft.com/en-us/teams/notifications-settings/troubleshoot-notifications-in-microsoft-teams-mobile-apps).

Use **Block during quiet hours** to quiet work notifications outside **Monday-Friday, 10:14-18:14 Europe/Warsaw**: the intended weekday quiet interval is 18:14 through 10:14 the next morning, with Saturday and Sunday quiet all day. Check how the installed app handles overnight ranges and day boundaries. If a time picker cannot represent 10:14 or 18:14, record the limitation for manual review and an explicit choice of approximation; do not silently round. Teams bases quiet hours on device time, so retest after travel and verify that the intended Warsaw work boundary still holds. [Teams quiet time](https://support.microsoft.com/en-us/teams/platform/quiet-time-in-microsoft-teams-for-mobile-devices).

The optional **Set on Teams and Outlook** setting synchronizes schedules across those mobile apps on the same account and shares the schedule with Viva Insights. Microsoft says enabling that schedule synchronization cannot be reversed; decide separately whether you want it. Repository status export does not require this option. [Teams quiet time](https://support.microsoft.com/en-us/teams/platform/quiet-time-in-microsoft-teams-for-mobile-devices).

## Garmin: filter mirrored apps separately

In Garmin Connect on Android, use **More/menu > Settings > Notifications > App Notifications** and select the apps allowed to send notifications to the watch. Include every communicator app whose personal direct messages you want. Garmin's app-level switch cannot express "direct messages only" within an app; remove unwanted categories in that app or in Android first, and test the resulting mirrored notifications. The fēnix 9 manual says the watch's **Blocked Apps** list shows excluded Android apps. [Garmin Android app selection](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-043F879B-FC35-4B22-A025-DF91C157B13F.html).

The same manual places phone notification controls at **Watch Settings > Connectivity > Phone > Notifications**. Review calls, texts, apps, privacy, and timeout there. Sleep and activity notification behavior belongs to **Focus Modes**; changes made with a focus mode active apply to that mode. Check normal use, sleep, and activities separately. [Phone notification controls](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-043F879B-FC35-4B22-A025-DF91C157B13F.html), [Focus Modes](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-DF71C212-09EF-431B-87E9-40DEBD0C41A6.html).

If the installed Garmin Connect app offers **Follow Do Not Disturb Behavior**, inspect and test it before recording it as working. A current primary Garmin support document confirming this option's behavior was not found in this review. Do not assume it synchronizes the watch's DND state, its native alerts, or silent Android channels. Record whether the option exists and test an allowed notification with phone DND both on and off.

### Watch-native alerts

Garmin notifications generated by the watch have their own settings. Under **Watch Settings > Notifications & Alerts > Health & Wellness**, review daily summaries, stress/rest messages, move reminders, and goal alerts. Keep the prompts you use. Preserve abnormal-heart-rate alerts during the initial cleanup. [fēnix 9 Health and Wellness Alerts](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-EB335B47-6770-4A06-8EEC-8E0355507102.html).

Phone-connect/disconnect alerts are under **Watch Settings > Notifications & Alerts > System Alerts > Phone**. If repeated connection notices are the distraction, change that alert setting after confirming the connection itself is reliable. [fēnix 9 Phone Connection Alerts](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-1E446357-A244-44C2-BF72-DE150D68F292.html).

Keep Garmin Connect and Garmin Messenger operational while tuning notifications. Assistance, incident detection, tracking, and inReach communication have their own connectivity requirements and are outside the notification cleanup. Review their configuration without triggering an SOS, assistance request, or incident test. A working mirrored phone notification does not verify satellite or emergency features. [fēnix 9 safety and tracking](https://www8.garmin.com/manuals/webhelp/GUID-708A8F4D-9A78-49CF-9528-DE109BBCC472/EN-US/GUID-64F677A5-03E0-453F-BFE3-E1B93D6FA3FC.html), [inReach feature requirements](https://www.garmin.com/en-US/connectivity/smartwatches/fenix-9-pro/feature-requirements/).

## Keep repository state useful

The intended workflow is:

1. Review `config/policy.json`: desired app rules and manual settings belong here.
2. Connect the phone and run `scan`, then `plan`. Read the proposed package changes.
3. Run `apply --yes` when the proposed changes match your choices. Save the transaction reference; `restore TRANSACTION --yes` restores the permission state recorded for that transaction, subject to the command's checks.
4. Complete the manual phone, app, and watch settings above. Run the practical checks below.
5. Record each manual rule with `attest RULE_ID --result pass` or `fail`; `--note` can record the device/firmware context and what you observed. Avoid private message contents, contact names, or account details.
6. Run `status --export` to refresh `state/status.json` and `state/status.md`, and review the diff before committing. These summaries omit device serials and app inventory.

An attestation is a dated human observation. It is not a live readback from Garmin, Teams, or ColorOS. A scan checks only the Android permission state supported by this tool. The repository does not automatically discover every manual change or continuously synchronize a disconnected device. Reconnect and scan to discover measured drift; recheck manual settings and renew their attestations when they change. Keep the desired policy distinct from both measured state and manual observations.

## Practical verification

Use benign test events and compare both devices:

- One wanted notification from an allowed app: check phone sound/banner and watch behavior independently.
- One unwanted category: confirm the interruption is gone while the app still works as intended.
- One app kept on the phone but blocked in Garmin Connect: confirm it stays on the phone and does not alert the watch.
- Phone DND on and off: check the wanted call/message exception and an ordinary notification. Record whether Garmin follows it.
- A short clock alarm with phone locked, sleep/DND active and Garmin disconnected: confirm it sounds, then verify the recurring weekday 10:09 alarm remains enabled. Record `test.wake_alarm` separately.
- A Teams message while active on desktop, then after desktop inactivity. Check a Teams call separately.
- Work notifications around 10:14 and 18:14 on a weekday, and during the weekend. Confirm personal direct messages still arrive outside work hours.
- Watch normal, sleep, and activity modes: check the intended notification behavior and an ordinary local alarm.
- After a phone/watch reboot or Bluetooth reconnect: confirm the chosen behavior and normal Garmin synchronization still work.

Repeat relevant checks after OS, watch firmware, Teams, or Garmin Connect updates; app reinstall or data reset; a new notification category; profile/account changes; a new phone/watch; time-zone travel; or a change to the policy. Record failed checks honestly and adjust the responsible setting before marking them passed.
