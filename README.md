# Healthier Notifications

[![Tests](https://github.com/PawelTroka/healthier-notifications/actions/workflows/tests.yml/badge.svg)](https://github.com/PawelTroka/healthier-notifications/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![No Python dependencies](https://img.shields.io/badge/Python_dependencies-none-2E7D32)

**Fewer interruptions, with calls, personal messages and wake-up alarms preserved.**

A local Python toolkit for keeping Android phone and Garmin watch notification policy in Git. Inspect the phone, preview supported changes, apply with a rollback journal, and see which settings still need a manual check.

[Quick start](#quick-start-without-a-phone) · [Device setup](docs/device-guide.md) · [Policy](config/policy.json) · [Privacy](#files-and-privacy) · [Contributing](CONTRIBUTING.md)

## Quick start without a phone

With Python 3.10+ installed:

```sh
git clone https://github.com/PawelTroka/healthier-notifications.git
cd healthier-notifications
python -m healthier_notifications validate
python -m healthier_notifications --policy examples/policy.demo.json plan --snapshot examples/snapshot.demo.json
python -m unittest discover -s tests -v
```

The demo uses synthetic data and makes no device calls. For the real phone, continue with [first-run setup](#first-run-when-the-phone-is-connected).

## Included personal policy

This repo includes the maintainer's policy. Review it before using it on another device:

| Priority | Desired behavior |
| --- | --- |
| Calls and personal direct messages | Keep across communicator apps; separate from work quiet hours |
| Actionable work | Monday–Friday, **10:14–18:14**, Europe/Warsaw |
| Clock alarms | Preserve during quiet hours and sleep/DND; retain weekday **work prep at 10:12** and **work now at 10:14** |
| Deliberate reminders and safety/security alerts | Preserve |
| Groups, promotions, reactions and other noise | Disable at the source where separable; record remaining mixed categories |

The private profile records confirmed sleep choices. The public template leaves sleep hours unset and app rules empty; the installed-app inventory and personal profile stay in ignored `.local/` files. The first connected session on **2026-09-15** inspected an OPPO Find X9 Ultra (CPH2841), Android 16. The user confirmed that the original enabled weekday alarms—**work prep at 10:12** and **work now at 10:14**—were correct. Moving work prep to 10:09 was a setup mistake; the corrected policy preserves the original pair and requests no additional alarm. Device restoration is pending readback in the [session report](docs/hardware-session.md#alarm-time-correction). **A test alarm sounded clearly with the phone locked, DND active and Bluetooth off.** The temporary alarm was removed and Bluetooth/DND restored. The user also confirmed one incoming alert reached both phone and watch. The stricter alarm test during work quiet hours and broader notification tests remain pending.

Garmin Connect identified **fenix 9 Pro - inReach, 51mm**, firmware **6.38**. The forwarding list was saved with 19 selected entries, and **Follow Do Not Disturb Behavior** was enabled. Native calls/texts/apps vibration was on; goal alerts and morning/evening reports were turned off. The watch sleep schedule now matches the confirmed private phone schedule, including Saturday's extension. Sleep Focus notifications stayed on, manual system DND stayed off, and a requested sync was followed by a Connected device status. A single incoming alert reached both devices; delivery from every app and focus behavior still need testing. See the [connected-session report](docs/hardware-session.md) for the configuration and remaining checks.

Teams and the selected Outlook work account have quiet hours **18:14–10:14**, plus all-day Saturday/Sunday quiet. Personal Outlook settings were preserved. Source filters were configured for selected messaging apps; Outlook calendar reminders use separate controls.

## What can be synchronized

| Setting | Implementation | How state is checked |
| --- | --- | --- |
| Whole-app Android notification permission | Explicit reviewed `allow`/`block` rules on supported Android 13+ devices | ADB reads the selected user's runtime permission before/after changes |
| Direct messages versus groups, promotions, reactions | Guided Android channels and in-app settings | Dated manual checks and delivery tests |
| Work schedule and desktop duplicate suppression | Guided in-app setup using the hours above | Manual check; the Python process is not a running scheduler |
| Clock alarms, including the existing weekday pair | Preserve the clock app, existing labels/times and quiet-mode exceptions on the device | Clock configuration readback and a locked-phone alarm test during DND, without the watch connected |
| Garmin forwarded-app allowlist | Guided Garmin Connect settings, with each chosen app recorded in policy | Per-app manual checks |
| Watch focus, native wellness alerts and sleep | Guided watch setup | Manual checks against the actual model/firmware |

The repo holds **desired settings**, **observed Android permissions**, and **manual observations** separately. A successful permission check does not prove direct-message filtering or watch delivery. Manual checks expire after 30 days and become stale after a policy change, phone/user change, or phone OS build change. Watch firmware and app updates require a manual recheck; this tool cannot detect watch configuration changes.

## First run when the phone is connected

### 1. Install Platform-Tools and connect the phone

Python 3.10+ and Google's **Android SDK Platform-Tools** are required. There are no Python packages to install. Platform-Tools is not included in Git. The maintainer's original Windows workspace already has portable ADB in `.tools/platform-tools`; fresh clones need the setup below.

Download Platform-Tools for your operating system from [Google's download page](https://developer.android.com/tools/releases/platform-tools) and extract its `platform-tools` folder into `.tools` in this repo. On Windows:

```text
healthier-notifications/
  .tools/
    platform-tools/
      adb.exe
      AdbWinApi.dll
      AdbWinUsbApi.dll
```

Alternatively put `adb` on PATH, set `ANDROID_HOME` to your installed SDK, or pass `--adb "C:\path\to\adb.exe"`. Keep the ZIP's companion files with `adb.exe`. On Linux/macOS, the same Python commands work with the corresponding `adb` executable.

Enable Developer options and USB debugging on the phone, connect it with a data-capable USB cable, unlock it and approve this computer's debugging key. These on-device steps are required. [Android connection instructions](https://developer.android.com/tools/adb#Enabling).

### 2. Discover and classify the actual apps

From PowerShell in this folder:

```powershell
python -m healthier_notifications validate
python -m healthier_notifications init
```

The inventory is saved to `.local/latest.json`. New apps in `.local/policy.draft.json` start with `phone: "preserve"`, `watch: "review"`, and `reviewed: false`. Existing app choices are retained in the draft. Drafts have `local_only: true`, which prevents exporting their app list to tracked `state/` files. `init` does not edit the main policy or change the phone.

Review the draft as a private policy, for example by saving a working copy as `.local/policy.personal.json`. Keep `local_only: true` in that copy. The draft contains third-party apps; consult the full inventory for preinstalled messaging/calendar apps and add their watch choices manually. Match an unfamiliar package to its phone settings page:

```powershell
python -m healthier_notifications open-settings --package com.microsoft.teams
```

This only opens a settings screen. It works for an installed package whose settings activity the firmware supports.

Use `category: "messages"` for your personal communicator apps and `"work"` for dedicated work apps. Keep `phone: "preserve"` while filtering their unwanted notifications using the [device guide](docs/device-guide.md). Mark the rule reviewed when identified and choose `watch: "allow"` or `"block"`. For communicators carrying both work and personal conversations, use account/conversation controls so work quiet hours do not silence personal messages.

Only select `phone: "block"` for an app whose **entire ordinary notification stream** you want off. The tool restricts that action to reviewed `noise` or `admin` apps. Use manual silent/category settings for an app that still has useful notifications. `phone: "allow"` can restore a supported app's denied notification permission; it does not enable its channels, bypass quiet time, or configure Garmin.

For a private profile, put `--policy` before every command that uses its choices:

```powershell
python -m healthier_notifications --policy .local/policy.personal.json validate
python -m healthier_notifications --policy .local/policy.personal.json plan
python -m healthier_notifications --policy .local/policy.personal.json checks
python -m healthier_notifications --policy .local/policy.personal.json status > .local/status.personal.md
```

Use the same option for `apply` and `attest`. Status without `--export` prints a report; the example redirects it into an ignored local file. A status needing review returns exit code 2 and still produces the report. Manual checks are tied to the selected policy's hash, so a private-profile check does not establish a pass for a different public policy.

Only copy app rules into `config/policy.json` when you intend to publish those names and choices. To publish an inventory-derived policy, first remove private app rules and custom instructions, review the result, and then deliberately remove `local_only` or set it to `false`. The flag prevents CLI export; it does not prevent manually adding a private file to Git.

### 3. Preview, then apply the reviewed permission rules

```powershell
python -m healthier_notifications plan
python -m healthier_notifications apply --yes
```

`plan` and `apply` without `--yes` are previews. Applying performs fresh checks and prints the rollback journal path before the first permission write. System/preinstalled apps, protected phone/SMS/clock/Garmin components, shared-UID apps, fixed permissions, unknown states and unsupported builds need manual settings. No app is disabled or uninstalled. New/unclassified apps are reported for review, and are never blocked automatically.

For several connected devices, choose one explicitly. Global options go **before** the command:

```powershell
python -m healthier_notifications --serial YOUR_SERIAL plan
python -m healthier_notifications --serial YOUR_SERIAL --user 10 scan
```

Without `--user`, the current Android user is selected. A work profile is a separate Android user: inspect its actual ID using `adb shell pm list users`, then use separate `--policy` and `--local-dir` paths for each profile to keep its policy and history distinct. Phone-wide DND and watch behavior still require a combined manual test.

### 4. Configure the phone and watch, then record checks

Follow [the phone/watch guide](docs/device-guide.md). It covers communicator categories, Teams duplicates/quiet time, Garmin allowlisting, native watch alerts and realistic delivery tests. The selected work hours are recorded in the repo; this version applies the schedule through guided in-app setup.

Preserve the original enabled weekday alarms: **work prep at 10:12** and **work now at 10:14**. `schedule.wake_alarm` is `null` because no separate new wake-up alarm is requested. The earlier 10:09 suggestion does not authorize changing or adding an alarm. Complete `test.wake_alarm` by checking the existing pair and alarm audibility through quiet settings. A locked-phone DND sound test passed with Bluetooth off; it ran during work hours, so the full check still requires testing while work quiet hours are active. Keep clock app rules as `phone: "preserve"`; use category `reminders` for any third-party alarm app.

```powershell
python -m healthier_notifications checks
```

After actually completing a check, record its outcome with the phone connected:

```powershell
python -m healthier_notifications attest phone.work --result pass --note "Verified weekday 10:14-18:14 and desktop-active suppression"
python -m healthier_notifications attest watch.allowlist --result pass --note "Checked on watch; record model and firmware here"
```

Use `--result fail` for a failed check. A chosen app's `watch` rule adds a check such as `app:com.microsoft.teams:watch`. Check notes stay local. The tool does not infer successful Garmin configuration from a phone connection.

### 5. Refresh the shared state

```powershell
python -m healthier_notifications status --export
git diff -- config state
git status --short
```

`state/status.json` and `state/status.md` summarize the observation time, Android permission differences, app classification still needed, and manual check results. They include every app rule and manual instruction in the selected policy. `local_only` policies cannot use `--export`; select the reviewed public policy for a shared summary. With empty public app rules, the export contains app-review counts but no installed-app names, and does not describe the private profile's progress. `needs-review` is expected until setup and tests are complete. New files appear in `git status`; inspect them before adding them to Git.

For each later reconciliation: connect → `plan` → apply wanted permission changes → recheck affected manual settings → `status --export`. If you prefer a change you made on a device, update the desired policy first instead of applying the old policy back to it. This is explicit reconciliation whenever you run the commands, not continuous or automatic two-way device synchronization.

## Policy format

`config/policy.json` is the source of desired settings. An app rule looks like:

```json
{
  "package": "com.example.chat",
  "label": "My communicator",
  "category": "messages",
  "phone": "preserve",
  "watch": "allow",
  "reviewed": true,
  "note": "Keep direct messages and calls; disable groups inside the app unless explicitly selected."
}
```

Replace the example package with one from your inventory. Supported categories: `calls`, `messages`, `work`, `reminders`, `safety`, `security`, `noise`, `admin`, `other`. Phone choices: `preserve`, `allow`, `block`. Watch choices: `review`, `allow`, `block`. Watch choices are manual targets, not ADB writes. Conflicting phone-block/watch-allow rules are rejected.

Put extra app/category requirements in `manual_rules`, with a unique `id`, `device` (`phone`, `watch`, `both`) and `instruction`. Keep instructions aligned with `schedule`; changing JSON alone does not schedule device behavior. Run `validate` after editing.

## Restore a permission change

Use the exact journal printed by `apply`:

```powershell
python -m healthier_notifications restore .local\transactions\JOURNAL_ID.json
python -m healthier_notifications restore .local\transactions\JOURNAL_ID.json --yes
```

Restore verifies the original serial, Android user, OS build, package UID/version and permission state. It refuses conflicting later edits. Already-restored permissions are skipped, and a partial restore can be retried. After multiple applies, restore newest journals first.

If USB disconnects or a command times out after a write, the journal already records the attempt. Reconnect, preview that journal's restore and inspect its result. A failed verification is not reported as success. Unexpected permission-flag changes need manual inspection; the tool never clears flags. This restores only recorded notification grants, not manual channel/Garmin/schedule edits, old notifications, or a whole-device backup. Update policy before the next apply if you want the restored behavior to remain desired.

## Offline use and verification

No phone or ADB is needed for these commands:

```powershell
python -m healthier_notifications validate
python -m healthier_notifications checks
python -m healthier_notifications --policy examples\policy.demo.json plan --snapshot examples\snapshot.demo.json
python -m unittest discover -s tests -v
```

The demo is synthetic and never claims to describe your devices. A saved local snapshot can also be used with `plan --snapshot .local/latest.json` or `status --snapshot .local/latest.json`. The observation time remains visible; snapshots older than 24 hours cannot yield a current successful status. `apply` and `restore` always inspect the live phone.

Exit codes: `0` = successful command (or completed status), `1` = error/refused operation, `2` = plan blockers or status needing review, `130` = interrupted. A permission difference in a valid plan is normal and returns `0`.

PowerShell shorthand: `./notifications.ps1 plan` runs the same CLI from any directory. If local script execution is disabled, use the `python -m` commands directly from the repo; no execution-policy change is necessary.

## Files and privacy

| Path | Purpose | Suitable for Git? |
| --- | --- | --- |
| `config/policy.json` | Desired app choices, work hours and manual requirements | Yes; review app names/notes for personal information |
| `state/status.json`, `state/status.md` | Curated observation and manual-check summary | Yes, after review |
| `.local/latest.json` | Complete installed package metadata and selected permission states | Ignored; contains device serial and app inventory |
| `.local/policy.draft.json` | Private inventory-derived policy draft | Ignored until intentionally merged |
| `.local/policy.personal.json`, `.local/status.personal.md` | Private app choices and local report | Ignored; keep `local_only: true` in the policy |
| `.local/manual-checks.json` | Dated manual observations and free-text notes | Ignored |
| `.local/transactions/` | Write-ahead rollback journals | Ignored; retain locally for recovery |
| `.tools/` | Local portable ADB installation (install for a fresh clone) | Ignored |

The program reads package metadata, role holders and notification permission state. It does not collect notification bodies, conversations or contact lists, install an on-phone agent, or use a cloud notification classifier. Exported status omits serials, build fingerprints, unconfigured inventory entries and free-text attestation notes; it includes every configured app's package, label, permission observation and watch choice, plus manual instructions from policy. An inventory-derived policy can therefore expose an app list unless kept private. `local_only: true` rejects export before observing the phone or printing the report. Keep custom `--local-dir` locations private too.

## Validation limits

The mocked tests exercise parsing, device selection, permission controls, blocked writes, partial failures, rollback, private-profile export refusal and status reporting. GitHub Actions runs them on Windows and Linux with Python 3.10 and 3.14. Live OPPO inventory, selected phone/watch configuration readbacks, the locked-phone DND alarm sound test and one user-confirmed incoming alert on both devices completed. Automated permission changes, alarm delivery during work quiet hours and the broader notification tests are **not yet verified on hardware**. ColorOS may reject commands or expose different permission output; unknown state stops automated changes. Calls/media can have Android notification-permission exemptions, and individual channels, app settings, connectivity and watch focus modes can still affect delivery.

See [sources and capability boundaries](docs/sources.md) for official Android, OPPO, Garmin and Microsoft references. Start a connected session with `init`; then use real delivery tests before relying on the setup.
